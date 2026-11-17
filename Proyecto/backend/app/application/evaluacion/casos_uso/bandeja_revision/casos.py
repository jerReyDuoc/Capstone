"""Caso de uso de la bandeja de revisión (HU-22): composición de los mixins por responsabilidad."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.application.evaluacion.casos_uso.bandeja_revision.clasificaciones_bandeja import ClasificacionesBandejaMixin
from app.application.evaluacion.casos_uso.bandeja_revision.detalle_bandeja import DetalleBandejaMixin
from app.application.evaluacion.casos_uso.bandeja_revision.eventos_bandeja import EventosBandejaMixin


class BandejaRevision(ClasificacionesBandejaMixin, EventosBandejaMixin, DetalleBandejaMixin):
    def __init__(self, session: AsyncSession, umbral_confianza: float):
        self.s = session
        self.repo = fabricas().bandeja_revision(session)
        self.umbral = umbral_confianza
