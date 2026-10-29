"""
HU-15 · Grafo del agente (LangGraph). Ver el diagrama en __init__.py.

Las dependencias (gateway, filtro) NO viajan en el estado: van en
`config["configurable"]`, así el grafo se compila una sola vez por proceso y el estado
solo lleva datos.

HU-18: el nodo "guardia" usa el filtro de entrada del agente (categorías de ataque, ataques
en varios turnos y antecedentes neutralizados) y el tutor pasa por "validar_salida"
(canario, fuga del prompt, código, enlaces y alcance) antes de anclarse al contexto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.application.ai.agente import salida as validacion
from app.application.ai.gateway import AIGateway, ResultadoIA
from app.application.ai.politicas import TareaIA
from app.domain.ports.filtro_agente_port import CategoriaAtaque, FiltroAgentePort, ResultadoFiltro
from app.domain.ports.prompt_guard_port import PromptGuardPort
from app.domain.ports.registro_ia_port import ContextoLlamada


class SkillIA(str, Enum):
    VALIDAR_EVIDENCIA = "validar_evidencia"
    TUTOR = "tutor"


BLOQUEAR = "bloquear"        # un ataque en el campo corta la ejecución (sin NER ni LLM)
NEUTRALIZAR = "neutralizar"  # se quita la línea con el ataque y la ejecución sigue


@dataclass(frozen=True)
class SpecSkill:
    tarea: TareaIA
    # Qué hace la guardia con cada campo no confiable. En evidencias no actúa: lo hace
    # ProcessEvidenceUseCase (con MODO_SEGURIDAD_EVIDENCIA bloquear/marcar). En el tutor, el
    # mensaje se bloquea y los antecedentes guardados de la empresa se neutralizan (HU-18):
    # una justificación con inyección no debe impedir que el usuario use el tutor.
    campos: dict[str, str] = field(default_factory=dict)

    @property
    def guardia(self) -> bool:
        return bool(self.campos)


SKILLS: dict[SkillIA, SpecSkill] = {
    SkillIA.VALIDAR_EVIDENCIA: SpecSkill(TareaIA.VALIDAR_EVIDENCIA),
    SkillIA.TUTOR: SpecSkill(TareaIA.TUTOR, {"mensaje": BLOQUEAR, "antecedentes": NEUTRALIZAR}),
}

MOTIVO_INYECCION = CategoriaAtaque.INYECCION.value
ANTECEDENTE_OMITIDO = "(antecedente omitido por seguridad)"


class EstadoAgente(TypedDict, total=False):
    skill: str
    textos: dict[str, str | None]
    datos: dict[str, Any]
    contexto: ContextoLlamada
    bloqueado: bool
    motivo: str | None
    regla: str | None
    campo_bloqueado: str | None
    neutralizados: list[dict]
    salida_bloqueada: str | None
    resultado: ResultadoIA | None


@dataclass
class SalidaAgente:
    skill: SkillIA
    resultado: ResultadoIA | None = None
    bloqueado: bool = False
    motivo: str | None = None              # HU-18: categoría del ataque (inyeccion, jailbreak...)
    campo_bloqueado: str | None = None
    advertencias: list[str] = field(default_factory=list)
    regla: str | None = None               # regla del filtro que disparó (sin texto)
    neutralizados: list[dict] = field(default_factory=list)   # antecedentes omitidos {ref, categoria}
    salida_bloqueada: str | None = None    # la respuesta del LLM se reemplazó (fuga_canario, fuga_prompt)


class _FiltroSoloGuard(FiltroAgentePort):
    """Compatibilidad: sin filtro del agente, la guardia usa solo PromptGuardPort."""

    def __init__(self, guard: PromptGuardPort):
        self.guard = guard

    def evaluar(self, texto, previos=None) -> ResultadoFiltro:
        if texto and self.guard.detectar_inyeccion(texto):
            return ResultadoFiltro(True, CategoriaAtaque.INYECCION, "seguridad")
        return ResultadoFiltro.limpio()


# ------------------------------------------------------------------ nodos
def _deps(config: RunnableConfig) -> dict:
    return (config or {}).get("configurable", {})


async def nodo_guardia(estado: EstadoAgente, config: RunnableConfig) -> dict:
    """Revisa los textos no confiables ANTES del NER y del LLM (HU-18: por categoría de ataque)."""
    spec = SKILLS[SkillIA(estado["skill"])]
    filtro: FiltroAgentePort | None = _deps(config).get("filtro")
    if not spec.guardia or filtro is None:
        return {"bloqueado": False}
    datos = estado.get("datos") or {}
    textos = dict(estado.get("textos") or {})
    neutralizados: list[dict] = []
    for campo, politica in spec.campos.items():
        texto = textos.get(campo)
        if not texto:
            continue
        if politica == BLOQUEAR:
            r = filtro.evaluar(texto, datos.get("previos_usuario"))
            if r.bloquear:
                return {"bloqueado": True, "motivo": r.categoria.value, "regla": r.regla, "campo_bloqueado": campo}
        else:  # NEUTRALIZAR: línea por línea ("[REF] antecedente")
            lineas = []
            for linea in texto.splitlines():
                r = filtro.evaluar(linea)
                if r.bloquear:
                    ref = linea.split("]", 1)[0].lstrip("[") if linea.startswith("[") else None
                    neutralizados.append({"campo": campo, "ref": ref, "categoria": r.categoria.value, "regla": r.regla,
                                          "texto": linea})  # para el evento de seguridad (se anonimiza allí)
                    lineas.append(f"[{ref}] {ANTECEDENTE_OMITIDO}" if ref else ANTECEDENTE_OMITIDO)
                else:
                    lineas.append(linea)
            textos[campo] = "\n".join(lineas)
    cambios: dict = {"bloqueado": False, "textos": textos, "neutralizados": neutralizados}
    if SkillIA(estado["skill"]) == SkillIA.TUTOR:
        # HU-18: código de control (canario) distinto en cada llamada; nunca debe salir en la respuesta
        cambios["datos"] = {**datos, "canario": validacion.generar_canario()}
    return cambios


def _router(estado: EstadoAgente) -> str:
    """Router determinista: la skill la decide la lógica de negocio, no el modelo."""
    if estado.get("bloqueado"):
        return END
    return SkillIA(estado["skill"]).value


async def _ejecutar_tarea(estado: EstadoAgente, config: RunnableConfig) -> dict:
    gateway: AIGateway = _deps(config)["gateway"]
    spec = SKILLS[SkillIA(estado["skill"])]
    resultado = await gateway.ejecutar(
        spec.tarea, textos=estado["textos"], datos=estado.get("datos") or {}, contexto=estado.get("contexto"),
    )
    return {"resultado": resultado}


async def nodo_validar_evidencia(estado: EstadoAgente, config: RunnableConfig) -> dict:
    return await _ejecutar_tarea(estado, config)


async def nodo_tutor(estado: EstadoAgente, config: RunnableConfig) -> dict:
    return await _ejecutar_tarea(estado, config)


def _resultado(base: ResultadoIA, data) -> ResultadoIA:
    return ResultadoIA(
        data=data, traza_id=base.traza_id, prompt_version=base.prompt_version, modelo=base.modelo,
        advertencias=list(base.advertencias), sanitizado=base.sanitizado,
        textos_sanitizados=dict(base.textos_sanitizados), entidades_anonimizadas=base.entidades_anonimizadas,
    )


async def nodo_validar_salida(estado: EstadoAgente, config: RunnableConfig) -> dict:
    """
    HU-18: lo que el modelo devolvió se revisa antes de mostrarse. Una fuga del system prompt
    (canario o frases del prompt) reemplaza la respuesta completa; código, enlaces y contenido
    fuera de alcance se limpian. El gateway ya dejó estos problemas como advertencias.
    """
    from app.application.ai.prompts.tutor import SYSTEM

    resultado: ResultadoIA = estado["resultado"]
    canario = (estado.get("datos") or {}).get("canario")
    encontrados = validacion.problemas(resultado.data, canario, SYSTEM)
    if not encontrados:
        return {}
    bloqueante = next((p for p in encontrados if p in validacion.PROBLEMAS_BLOQUEANTES), None)
    return {
        "resultado": _resultado(resultado, validacion.aplicar(resultado.data, encontrados)),
        "salida_bloqueada": "fuga_prompt" if bloqueante else None,
    }


async def nodo_anclar_contexto(estado: EstadoAgente, config: RunnableConfig) -> dict:
    """
    Criterio 1 también a la salida: el tutor solo puede citar brechas de SU contexto. Las
    referencias que no existen se quitan (el gateway ya dejó la advertencia
    'brecha_fuera_de_contexto' en la métrica). Los pasos se renumeran y las sugerencias
    se acotan a 3.
    """
    resultado: ResultadoIA = estado["resultado"]
    contexto = (estado.get("datos") or {}).get("contexto")
    data = resultado.data
    refs = contexto.normalizar_referencias(list(data.brechas_referenciadas)) if contexto else []
    pasos = [p.model_copy(update={"orden": i}) for i, p in enumerate(
        sorted(data.pasos, key=lambda p: p.orden), start=1) if (p.accion or "").strip()]
    sugerencias = [s.strip() for s in data.sugerencias if (s or "").strip()][:3]
    # v1.1: la fuente normativa NO la escribe el modelo (inventaba números de artículo): es el
    # framework y el artículo reales de los controles que cita, tomados de la matriz.
    normativas = contexto.referencias_normativas(refs) if contexto else []
    limpio = data.model_copy(update={
        "brechas_referenciadas": refs, "pasos": pasos, "sugerencias": sugerencias,
        "referencias_normativas": normativas, "respuesta": (data.respuesta or "").strip(),
    })
    return {"resultado": _resultado(resultado, limpio)}


def construir_grafo():
    g = StateGraph(EstadoAgente)
    g.add_node("guardia", nodo_guardia)
    g.add_node(SkillIA.VALIDAR_EVIDENCIA.value, nodo_validar_evidencia)
    g.add_node(SkillIA.TUTOR.value, nodo_tutor)
    g.add_node("validar_salida", nodo_validar_salida)
    g.add_node("anclar_contexto", nodo_anclar_contexto)
    g.add_edge(START, "guardia")
    g.add_conditional_edges("guardia", _router, {
        END: END,
        SkillIA.VALIDAR_EVIDENCIA.value: SkillIA.VALIDAR_EVIDENCIA.value,
        SkillIA.TUTOR.value: SkillIA.TUTOR.value,
    })
    g.add_edge(SkillIA.VALIDAR_EVIDENCIA.value, END)
    g.add_edge(SkillIA.TUTOR.value, "validar_salida")
    g.add_edge("validar_salida", "anclar_contexto")
    g.add_edge("anclar_contexto", END)
    return g.compile()


_GRAFO = None


def grafo():
    """Grafo compilado (uno por proceso)."""
    global _GRAFO
    if _GRAFO is None:
        _GRAFO = construir_grafo()
    return _GRAFO


# ------------------------------------------------------------------ fachada
class AgenteIA:
    """
    Punto de entrada de la lógica de negocio a la IA. Las excepciones del gateway
    (CapaIAError: sanitización abortada, auditoría, LLM no disponible) salen tal cual.
    """

    def __init__(self, gateway: AIGateway, guard: PromptGuardPort | None = None,
                 filtro: FiltroAgentePort | None = None):
        self.gateway = gateway
        self.guard = guard
        # HU-18: el filtro del agente (infrastructure/security/filtro_agente.py). Sin él, la
        # guardia usa solo PromptGuardPort (comportamiento de HU-15).
        self.filtro = filtro or (_FiltroSoloGuard(guard) if guard is not None else None)

    async def ejecutar(
        self,
        skill: SkillIA,
        textos: dict[str, str | None],
        datos: dict[str, Any] | None = None,
        contexto: ContextoLlamada | None = None,
    ) -> SalidaAgente:
        skill = SkillIA(skill)
        estado: EstadoAgente = {
            "skill": skill.value, "textos": dict(textos), "datos": dict(datos or {}),
            "contexto": contexto or ContextoLlamada(), "bloqueado": False, "resultado": None,
            "neutralizados": [], "salida_bloqueada": None,
        }
        final = await grafo().ainvoke(
            estado, config={"configurable": {"gateway": self.gateway, "filtro": self.filtro}},
        )
        resultado: ResultadoIA | None = final.get("resultado")
        return SalidaAgente(
            skill=skill, resultado=resultado, bloqueado=bool(final.get("bloqueado")),
            motivo=final.get("motivo"), campo_bloqueado=final.get("campo_bloqueado"),
            advertencias=list(resultado.advertencias) if resultado else [],
            regla=final.get("regla"), neutralizados=list(final.get("neutralizados") or []),
            salida_bloqueada=final.get("salida_bloqueada"),
        )
