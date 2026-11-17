"""Lógica pura de la bandeja de revisión: qué motivos tiene una respuesta y cómo se prioriza."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.domain.models.respuesta import FuenteClasificacion
from app.application.evaluacion.casos_uso.bandeja_revision.comun import (
    BAJA_CONFIANZA, CONCORDANTE, DIVERGENCIA, MOTIVOS, MOTIVOS_PRIORITARIOS, RESUELTA_POR_LLM, SEGURIDAD,
    SIN_RESOLVER, _REQ, rango_criticidad,
)

# ===================================================================== lógica pura
@dataclass(frozen=True)
class EvidenciaLlm:
    """Lo mínimo de una evidencia para decidir los motivos (también se usa en las pruebas)."""
    id: int
    clasificacion_llm: str | None
    confianza: float | None
    fecha: date | None
    es_remediacion: bool = False
    estado_declarado: str | None = None


def ultima_del_llm(evidencias: list[EvidenciaLlm]) -> EvidenciaLlm | None:
    """La evidencia procesada por el LLM más reciente (por fecha y luego por id)."""
    procesadas = [e for e in evidencias if e.clasificacion_llm or e.confianza is not None]
    if not procesadas:
        return None
    return max(procesadas, key=lambda e: (e.fecha or date.min, e.id))


def calcular_motivos(*, declarado: str | None, estado_final: str | None, fuente: str | None,
                     evidencias: list[EvidenciaLlm], con_evento: bool, umbral: float) -> list[str]:
    """Motivos (en orden de urgencia) por los que la respuesta debe pasar por un humano."""
    motivos: set[str] = set()
    if con_evento or fuente == FuenteClasificacion.SEGURIDAD.value:
        motivos.add(SEGURIDAD)
    if estado_final == _REQ:
        motivos.add(SIN_RESOLVER)
    ultima = ultima_del_llm(evidencias)
    if ultima is not None:
        # en remediación (HU-17) lo "declarado" es lo que la empresa dice haber alcanzado
        base = ultima.estado_declarado if ultima.es_remediacion and ultima.estado_declarado else declarado
        segura = ultima.confianza is not None and ultima.confianza >= umbral
        if ultima.confianza is not None and ultima.confianza < umbral:
            motivos.add(BAJA_CONFIANZA)
        if ultima.clasificacion_llm:
            if base == _REQ:
                if segura:
                    motivos.add(RESUELTA_POR_LLM)
            elif base and ultima.clasificacion_llm != base:
                motivos.add(DIVERGENCIA)
            elif base and segura and not motivos:
                motivos.add(CONCORDANTE)
    return [m for m in MOTIVOS if m in motivos]


def esta_pendiente(clasificacion_revisada: str | None, fuente: str | None) -> bool:
    return clasificacion_revisada is None or fuente != FuenteClasificacion.REVISION.value


def es_prioritaria(motivos: list[str]) -> bool:
    return any(m in MOTIVOS_PRIORITARIOS for m in motivos)


def clave_prioridad(motivos: list[str], criticidad: str | None, fecha: datetime | date | None) -> tuple:
    primero = MOTIVOS.index(motivos[0]) if motivos else len(MOTIVOS)
    instante = fecha if isinstance(fecha, datetime) else (
        datetime.combine(fecha, datetime.min.time()) if isinstance(fecha, date) else datetime.min)
    return (primero, rango_criticidad(criticidad), -instante.timestamp() if instante != datetime.min else 0)
