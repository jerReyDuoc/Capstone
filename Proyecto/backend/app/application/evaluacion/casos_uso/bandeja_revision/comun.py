"""Constantes de motivos y orden de la bandeja de revisión (HU-22) y utilidades de criticidad."""
from __future__ import annotations

import unicodedata

from app.domain.models.respuesta import EstadoClasificacion

MAX_CANDIDATAS = 3000

SEGURIDAD = "seguridad"
DIVERGENCIA = "divergencia"
SIN_RESOLVER = "sin_resolver"
BAJA_CONFIANZA = "baja_confianza"
RESUELTA_POR_LLM = "resuelta_por_llm"
CONCORDANTE = "concordante"

# Orden de urgencia: lo primero que debe mirar el oficial
MOTIVOS = (SEGURIDAD, DIVERGENCIA, SIN_RESOLVER, BAJA_CONFIANZA, RESUELTA_POR_LLM, CONCORDANTE)
MOTIVOS_PRIORITARIOS = MOTIVOS[:-1]

ESTADOS_REVISION = ("pendiente", "revisada", "todas")
ORDENES = ("prioridad", "reciente")

_RANGO_CRITICIDAD = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
_REQ = EstadoClasificacion.REQUIERE_REVISION.value


def _sin_tildes(texto: str | None) -> str:
    base = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def rango_criticidad(criticidad: str | None) -> int:
    return _RANGO_CRITICIDAD.get(_sin_tildes(criticidad), 4)

