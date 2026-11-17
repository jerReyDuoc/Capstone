"""Consultas de la retención de usuarios temporales (HU-25)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.usuario_temporal import UsuarioTemporal


class RetencionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def contar_usuarios_sin_vencimiento(self) -> int:
        n = (await self.session.execute(
            select(func.count()).select_from(UsuarioTemporal)
            .where(UsuarioTemporal.fecha_anonimizacion.is_(None), UsuarioTemporal.fecha_expiracion.is_(None))
        )).scalar_one()
        return int(n)
