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
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel

from app.application.ai.prompts import tutor, validar_evidencia
from app.application.ai.prompts.base import PromptRenderizado
from app.application.schemas.evidence_validation import EvidenceValidation
from app.application.schemas.tutor import TipoRespuestaTutor, TutorRespuesta


class TareaIA(str, Enum):
    VALIDAR_EVIDENCIA = "validar_evidencia"
    TUTOR = "tutor"  # HU-15


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


def _validar_salida_evidencia(r: EvidenceValidation, _datos: dict[str, Any] | None = None) -> list[str]:
    """Reglas post-LLM que el schema no puede expresar. Generan advertencias auditables."""
    adv = []
    if not r.respalda_clasificacion_usuario and not (r.divergencia_explicada or "").strip():
        adv.append("divergencia_sin_explicar")
    if not (r.justificacion or "").strip():
        adv.append("justificacion_vacia")
    return adv


# ---------------------------------------------------------------- TUTOR (HU-15)
def _prompt_tutor(textos: dict[str, str], datos: dict[str, Any]) -> PromptRenderizado:
    return tutor.construir(
        mensaje=textos["mensaje"],
        contexto=datos["contexto"],
        nivel=datos["nivel"],
        historial=datos.get("historial"),
        antecedentes=textos.get("antecedentes") or "",
        foco=datos.get("foco"),
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
    # v1.1: números de artículo que no están en las fuentes del contexto (el modelo los inventaba)
    if datos and datos.get("contexto") is not None:
        validos = datos["contexto"].articulos_validos
        textos = [r.respuesta or ""] + [p.accion or "" for p in r.pasos] + [p.evidencia_esperada or "" for p in r.pasos]
        if any(n not in validos for t in textos for n in _CITA_ARTICULO.findall(t)):
            adv.append("articulo_no_verificado")
    return adv


def _etiqueta_tutor(r: TutorRespuesta) -> str:
    return r.tipo.value


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
    }
