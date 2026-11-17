"""Filtros y filas de trabajo de la bandeja de revisión."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models.evaluacion import Evaluacion
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.application.evaluacion.casos_uso.bandeja_revision.reglas_motivos import EvidenciaLlm


@dataclass
class FiltrosBandeja:
    vista: str = "clasificaciones"          # clasificaciones | eventos
    estado: str = "pendiente"               # pendiente | revisada | todas
    motivo: str | None = None               # uno de MOTIVOS (None = todos los prioritarios)
    evaluacion_id: int | None = None
    dominio_id: int | None = None
    criticidad: str | None = None
    origen: str | None = None               # solo eventos: justificacion | evidencia | tutor ...
    orden: str = "prioridad"
    page: int = 1
    size: int = 20


@dataclass
class _Fila:
    respuesta: Respuesta
    control: MatrizControl | None
    dominio: str | None
    evaluacion: Evaluacion | None
    empresa: str | None
    motivos: list[str] = field(default_factory=list)
    eventos: int = 0
    ultima: EvidenciaLlm | None = None


def _evidencias_llm(r: Respuesta) -> list[EvidenciaLlm]:
    return [EvidenciaLlm(id=e.id_evidencia, clasificacion_llm=e.clasificacion_llm, confianza=e.confianza,
                         fecha=e.fecha_procesada, es_remediacion=e.es_remediacion,
                         estado_declarado=e.estado_declarado)
            for e in (r.evidencias or [])]


def _iso(v) -> str | None:
    return v.isoformat() if v is not None else None
