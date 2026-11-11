"""
Políticas por tarea: el "router" de la capa de IA.

Cada tarea de negocio que necesita un LLM se declara aquí con TODO lo que la
gobierna: qué textos son no confiables (y se sanitizan) con su límite, qué
prompt versionado usa, qué schema debe devolver, límites de tokens/tiempo y
reglas de validación de la salida. La lógica de negocio solo dice QUÉ tarea quiere.

Para agregar una tarea nueva:
  1. Crear su prompt en app/application/ai/prompts/<tarea>.py con PROMPT_VERSION.
  2. Crear su schema Pydantic de salida.
  3. Registrar una PoliticaTarea en `crear_politicas`.
  4. (HU-15) Registrar la skill que la usa en el agente (app/application/ai/agente/skills.py).

Tareas registradas:
  VALIDAR_EVIDENCIA  evalúa si una evidencia respalda la clasificación de un control.
  TUTOR              HU-15: Agente IA Tutor del panel de formación (explicaciones y planes
                     de acción por nivel sobre las brechas de la empresa).
  REDACTAR_BORRADOR  HU-16: adapta cláusulas de una plantilla de cumplimiento (Política de uso
                     de LLM, Aviso de privacidad, PIA) al rubro y a las brechas de la empresa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel

from app.application.ai.prompts import borrador as prompt_borrador
from app.application.ai.prompts import tutor, validar_evidencia
from app.application.ai.prompts.base import PromptRenderizado
from app.application.ai.verificacion_salida import verificar_evidencia
from app.application.schemas.borrador import BorradorIA
from app.application.schemas.evidence_validation import EvidenceValidation
from app.application.schemas.tutor import TipoRespuestaTutor, TutorRespuesta


# HU-07: el gateway agrega a los datos de `validar_salida` los textos no confiables tal como
# salieron hacia el LLM (ya anonimizados), para verificar el respaldo de la salida.
TEXTOS_ENVIADOS = "_textos_enviados"


class TareaIA(str, Enum):
    VALIDAR_EVIDENCIA = "validar_evidencia"
    TUTOR = "tutor"  # HU-15
    REDACTAR_BORRADOR = "redactar_borrador"  # HU-16


def _sin_advertencias(_r: BaseModel, _datos: dict[str, Any] | None = None) -> list[str]:
    return []


def _clasificacion(r: BaseModel) -> str | None:
    return getattr(r, "clasificacion", None)


@dataclass(frozen=True)
class PoliticaTarea:
    tarea: TareaIA
    schema: type[BaseModel]
    prompt_version: str
    construir_prompt: Callable[[dict[str, str], dict[str, Any]], PromptRenderizado]
    # campo no confiable -> máximo de caracteres que se envían (None = sin límite)
    campos_no_confiables: dict[str, int | None]
    max_tokens_salida: int
    timeout_s: float
    temperatura: float = 0.0
    modelo: str | None = None  # None = el modelo por defecto del proveedor
    # Reglas post-salida (respuesta, datos confiables) -> advertencias auditables
    validar_salida: Callable[[BaseModel, dict[str, Any]], list[str]] = field(default=_sin_advertencias)
    # Qué se guarda en llamadas_llm.clasificacion (evidencias: la clasificación; tutor: el tipo)
    etiqueta_metrica: Callable[[BaseModel], str | None] = field(default=_clasificacion)


# ---------------------------------------------------------------- VALIDAR_EVIDENCIA
def _prompt_validar_evidencia(textos: dict[str, str], datos: dict[str, Any]) -> PromptRenderizado:
    return validar_evidencia.construir(
        evidencia=textos["evidencia"],
        justificacion=textos["justificacion"],
        control=datos.get("control"),
        respuesta=datos["respuesta"],
        brecha=datos.get("brecha"),
    )


def _validar_salida_evidencia(r: EvidenceValidation, datos: dict[str, Any] | None = None) -> list[str]:
    """
    Reglas post-LLM que el schema no puede expresar. Generan advertencias auditables (quedan en
    llamadas_llm.advertencias). HU-07: verificación sintáctica, de alucinaciones (afirmaciones
    sin respaldo en lo que recibió el modelo) y de fuga de contexto. Aquí solo se REGISTRAN;
    la decisión (revisión humana y alerta) la toma ProcessEvidenceUseCase con el mismo verificador.
    """
    datos = datos or {}
    textos = datos.get(TEXTOS_ENVIADOS) or {}
    respuesta = datos.get("respuesta")
    return verificar_evidencia(
        r,
        evidencia=textos.get("evidencia") if textos else None,
        justificacion=textos.get("justificacion"),
        control=datos.get("control"),
        brecha=datos.get("brecha"),
        declarado=getattr(respuesta, "estado_clasificacion", None),
        system_prompt=validar_evidencia.SYSTEM,
    ).codigos


# ---------------------------------------------------------------- TUTOR (HU-15)
def _prompt_tutor(textos: dict[str, str], datos: dict[str, Any]) -> PromptRenderizado:
    return tutor.construir(
        mensaje=textos["mensaje"],
        contexto=datos["contexto"],
        nivel=datos["nivel"],
        historial=datos.get("historial"),
        antecedentes=textos.get("antecedentes") or "",
        foco=datos.get("foco"),
        canario=datos.get("canario"),
    )


# "art. 20", "artículo 14", "cláusula 5.2", "sección 3.1"
_CITA_ARTICULO = re.compile(r"(?:art[íi]culo|art\.|cl[áa]usula|secci[óo]n)\s*(\d+(?:\.\d+)*)", re.IGNORECASE)


def _validar_salida_tutor(r: TutorRespuesta, datos: dict[str, Any] | None = None) -> list[str]:
    """El tutor solo puede citar brechas del contexto aislado que se le entregó."""
    adv = []
    permitidas = datos["contexto"].referencias_validas if datos and datos.get("contexto") else frozenset()
    if any(c.strip() not in permitidas for c in r.brechas_referenciadas):
        adv.append("brecha_fuera_de_contexto")
    if r.tipo == TipoRespuestaTutor.PLAN_ACCION and not r.pasos:
        adv.append("plan_sin_pasos")
    if not (r.respuesta or "").strip():
        adv.append("respuesta_vacia")
    # HU-18: fugas del system prompt (canario, frases del prompt), código, enlaces y alcance.
    # Aquí solo se REGISTRAN en la métrica; el nodo "validar_salida" del agente las aplica.
    from app.application.ai.agente.salida import problemas
    adv += problemas(r, (datos or {}).get("canario"), tutor.SYSTEM)
    # v1.1: números de artículo que no están en las fuentes del contexto (el modelo los inventaba)
    if datos and datos.get("contexto") is not None:
        validos = datos["contexto"].articulos_validos
        textos = [r.respuesta or ""] + [p.accion or "" for p in r.pasos] + [p.evidencia_esperada or "" for p in r.pasos]
        if any(n not in validos for t in textos for n in _CITA_ARTICULO.findall(t)):
            adv.append("articulo_no_verificado")
    return adv


def _etiqueta_tutor(r: TutorRespuesta) -> str:
    return r.tipo.value


# ---------------------------------------------------------------- REDACTAR_BORRADOR (HU-16)
def _prompt_borrador(textos: dict[str, str], datos: dict[str, Any]) -> PromptRenderizado:
    return prompt_borrador.construir(
        plantilla=datos["plantilla"],
        contexto=datos["contexto"],
        instrucciones=textos.get("instrucciones") or "",
        prioritarias=list(datos.get("prioritarias") or []),
        canario=datos.get("canario"),
    )


def _validar_salida_borrador(r: BorradorIA, datos: dict[str, Any] | None = None) -> list[str]:
    """Solo REGISTRA en la métrica; el nodo "validar_borrador" del agente aplica las reglas."""
    if not datos or datos.get("plantilla") is None:
        return []
    from app.application.borradores.salida_ia import problemas
    return problemas(r, plantilla=datos["plantilla"], contexto=datos["contexto"],
                     canario=datos.get("canario"), system_prompt=prompt_borrador.SYSTEM)


def _etiqueta_borrador(r: BorradorIA) -> str:
    return f"secciones:{len(r.secciones)}"


def crear_politicas(
    *,
    max_chars_evidencia: int,
    max_chars_justificacion: int = 4000,
    max_tokens_salida: int = 1500,
    timeout_s: float = 60.0,
    modelo: str | None = None,
    max_chars_mensaje_tutor: int = 2000,
    max_chars_antecedentes_tutor: int = 6000,
    max_tokens_tutor: int | None = None,
    timeout_tutor_s: float | None = None,
    modelo_tutor: str | None = None,
    temperatura_tutor: float = 0.3,
    max_chars_instrucciones_borrador: int = 1500,
    max_tokens_borrador: int | None = None,
    timeout_borrador_s: float | None = None,
    modelo_borrador: str | None = None,
    temperatura_borrador: float = 0.2,
) -> dict[TareaIA, PoliticaTarea]:
    return {
        TareaIA.VALIDAR_EVIDENCIA: PoliticaTarea(
            tarea=TareaIA.VALIDAR_EVIDENCIA,
            schema=EvidenceValidation,
            prompt_version=validar_evidencia.PROMPT_VERSION,
            construir_prompt=_prompt_validar_evidencia,
            campos_no_confiables={
                "evidencia": max_chars_evidencia,
                "justificacion": max_chars_justificacion,
            },
            max_tokens_salida=max_tokens_salida,
            timeout_s=timeout_s,
            temperatura=0.0,
            modelo=modelo,
            validar_salida=_validar_salida_evidencia,
        ),
        TareaIA.TUTOR: PoliticaTarea(
            tarea=TareaIA.TUTOR,
            schema=TutorRespuesta,
            prompt_version=tutor.PROMPT_VERSION,
            construir_prompt=_prompt_tutor,
            # El historial ya se guardó anonimizado y va al prompt escapado entre delimitadores.
            # v1.1: también los antecedentes de la empresa (su justificación y el resultado de su
            # última evidencia en las brechas en foco), que son texto escrito por la empresa.
            campos_no_confiables={"mensaje": max_chars_mensaje_tutor, "antecedentes": max_chars_antecedentes_tutor},
            max_tokens_salida=max_tokens_tutor or max_tokens_salida,
            timeout_s=timeout_tutor_s or timeout_s,
            temperatura=temperatura_tutor,
            modelo=modelo_tutor or modelo,
            validar_salida=_validar_salida_tutor,
            etiqueta_metrica=_etiqueta_tutor,
        ),
        TareaIA.REDACTAR_BORRADOR: PoliticaTarea(
            tarea=TareaIA.REDACTAR_BORRADOR,
            schema=BorradorIA,
            prompt_version=prompt_borrador.PROMPT_VERSION,
            construir_prompt=_prompt_borrador,
            # Lo único que escribe la empresa: sus instrucciones de redacción. Las cláusulas, el
            # rubro, los puntajes y las brechas los arma el backend con datos de catálogo.
            campos_no_confiables={"instrucciones": max_chars_instrucciones_borrador},
            max_tokens_salida=max_tokens_borrador or max_tokens_salida,
            timeout_s=timeout_borrador_s or timeout_s,
            temperatura=temperatura_borrador,
            modelo=modelo_borrador or modelo,
            validar_salida=_validar_salida_borrador,
            etiqueta_metrica=_etiqueta_borrador,
        ),
    }
