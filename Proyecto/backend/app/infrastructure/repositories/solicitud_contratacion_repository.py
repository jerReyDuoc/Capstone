"""Repositorio de las solicitudes de contratación (HU-31)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.solicitud_contratacion import SolicitudContratacion


class SolicitudContratacionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def obtener_por_evaluacion(self, evaluacion_id: int) -> SolicitudContratacion | None:
        return await self.session.scalar(
            select(SolicitudContratacion).where(SolicitudContratacion.evaluacion_id == evaluacion_id))
