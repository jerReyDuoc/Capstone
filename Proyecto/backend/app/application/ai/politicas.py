"""
Políticas por tarea: el "router" de la capa de IA.

Cada tarea de negocio que necesita un LLM se declara aquí con TODO lo que la
gobierna: qué textos son no confiables (y se sanitizan) con su límite, qué
prompt versionado usa, qué schema debe devolver, límites de tokens/tiempo y
reglas de validación de la salida. La lógica de negocio solo dice QUÉ tarea quiere.

Para agregar una tarea nueva (p. ej. recomendaciones de ruta formativa):
  1. Crear su prompt en app/application/ai/prompts/<tarea>.py con PROMPT_VERSION.
  2. Crear su schema Pydantic de salida.
  3. Registrar una PoliticaTarea en `crear_politicas`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel

from app.application.ai.prompts import validar_evidencia
from app.application.ai.prompts.base import PromptRenderizado
from app.application.schemas.evidence_validation import EvidenceValidation


class TareaIA(str, Enum):
    VALIDAR_EVIDENCIA = "validar_evidencia"


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
    validar_salida: Callable[[BaseModel], list[str]] = field(default=lambda _r: [])


# ---------------------------------------------------------------- VALIDAR_EVIDENCIA
def _prompt_validar_evidencia(textos: dict[str, str], datos: dict[str, Any]) -> PromptRenderizado:
    return validar_evidencia.construir(
        evidencia=textos["evidencia"],
        justificacion=textos["justificacion"],
        control=datos.get("control"),
        respuesta=datos["respuesta"],
        brecha=datos.get("brecha"),
    )


def _validar_salida_evidencia(r: EvidenceValidation) -> list[str]:
    """Reglas post-LLM que el schema no puede expresar. Generan advertencias auditables."""
    adv = []
    if not r.respalda_clasificacion_usuario and not (r.divergencia_explicada or "").strip():
        adv.append("divergencia_sin_explicar")
    if not (r.justificacion or "").strip():
        adv.append("justificacion_vacia")
    return adv


def crear_politicas(
    *,
    max_chars_evidencia: int,
    max_chars_justificacion: int = 4000,
    max_tokens_salida: int = 1500,
    timeout_s: float = 60.0,
    modelo: str | None = None,
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
    }
