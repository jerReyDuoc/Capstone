"""
HU-15 · Grafo del agente (LangGraph). Ver el diagrama en __init__.py.

Las dependencias (gateway, guardia) NO viajan en el estado: van en
`config["configurable"]`, así el grafo se compila una sola vez por proceso y el estado
solo lleva datos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.application.ai.gateway import AIGateway, ResultadoIA
from app.application.ai.politicas import TareaIA
from app.domain.ports.prompt_guard_port import PromptGuardPort
from app.domain.ports.registro_ia_port import ContextoLlamada


class SkillIA(str, Enum):
    VALIDAR_EVIDENCIA = "validar_evidencia"
    TUTOR = "tutor"


@dataclass(frozen=True)
class SpecSkill:
    tarea: TareaIA
    # ¿El grafo revisa prompt injection en los textos antes del LLM? En evidencias lo hace
    # ProcessEvidenceUseCase (con MODO_SEGURIDAD_EVIDENCIA bloquear/marcar), así que no se
    # repite aquí; en el tutor lo hace el nodo "guardia".
    guardia: bool


SKILLS: dict[SkillIA, SpecSkill] = {
    SkillIA.VALIDAR_EVIDENCIA: SpecSkill(TareaIA.VALIDAR_EVIDENCIA, guardia=False),
    SkillIA.TUTOR: SpecSkill(TareaIA.TUTOR, guardia=True),
}

MOTIVO_INYECCION = "prompt_injection"


class EstadoAgente(TypedDict, total=False):
    skill: str
    textos: dict[str, str | None]
    datos: dict[str, Any]
    contexto: ContextoLlamada
    bloqueado: bool
    motivo: str | None
    campo_bloqueado: str | None
    resultado: ResultadoIA | None


@dataclass
class SalidaAgente:
    skill: SkillIA
    resultado: ResultadoIA | None = None
    bloqueado: bool = False
    motivo: str | None = None
    campo_bloqueado: str | None = None
    advertencias: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ nodos
def _deps(config: RunnableConfig) -> dict:
    return (config or {}).get("configurable", {})


async def nodo_guardia(estado: EstadoAgente, config: RunnableConfig) -> dict:
    """Bloquea ANTES del LLM (y antes del NER) los textos con prompt injection."""
    spec = SKILLS[SkillIA(estado["skill"])]
    guard: PromptGuardPort | None = _deps(config).get("guard")
    if not spec.guardia or guard is None:
        return {"bloqueado": False}
    for campo, texto in (estado.get("textos") or {}).items():
        if texto and guard.detectar_inyeccion(texto):
            return {"bloqueado": True, "motivo": MOTIVO_INYECCION, "campo_bloqueado": campo}
    return {"bloqueado": False}


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
    return {"resultado": ResultadoIA(
        data=limpio, traza_id=resultado.traza_id, prompt_version=resultado.prompt_version,
        modelo=resultado.modelo, advertencias=list(resultado.advertencias), sanitizado=resultado.sanitizado,
        textos_sanitizados=dict(resultado.textos_sanitizados),
    )}


def construir_grafo():
    g = StateGraph(EstadoAgente)
    g.add_node("guardia", nodo_guardia)
    g.add_node(SkillIA.VALIDAR_EVIDENCIA.value, nodo_validar_evidencia)
    g.add_node(SkillIA.TUTOR.value, nodo_tutor)
    g.add_node("anclar_contexto", nodo_anclar_contexto)
    g.add_edge(START, "guardia")
    g.add_conditional_edges("guardia", _router, {
        END: END,
        SkillIA.VALIDAR_EVIDENCIA.value: SkillIA.VALIDAR_EVIDENCIA.value,
        SkillIA.TUTOR.value: SkillIA.TUTOR.value,
    })
    g.add_edge(SkillIA.VALIDAR_EVIDENCIA.value, END)
    g.add_edge(SkillIA.TUTOR.value, "anclar_contexto")
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

    def __init__(self, gateway: AIGateway, guard: PromptGuardPort | None = None):
        self.gateway = gateway
        self.guard = guard

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
        }
        final = await grafo().ainvoke(
            estado, config={"configurable": {"gateway": self.gateway, "guard": self.guard}},
        )
        resultado: ResultadoIA | None = final.get("resultado")
        return SalidaAgente(
            skill=skill, resultado=resultado, bloqueado=bool(final.get("bloqueado")),
            motivo=final.get("motivo"), campo_bloqueado=final.get("campo_bloqueado"),
            advertencias=list(resultado.advertencias) if resultado else [],
        )
