"""Sesiones revocables de los usuarios con contraseña (HU-28)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.sesion_modelo import SesionUsuario


class SesionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def agregar(self, fila: SesionUsuario) -> None:
        self.session.add(fila)
        await self.session.flush()

    async def por_sid_hash(self, sid_hash: str) -> SesionUsuario | None:
        return await self.session.scalar(select(SesionUsuario).where(SesionUsuario.sid_hash == sid_hash))

    async def cerrar_todas(self, rol: str, actor_id: int, motivo: str, ahora: datetime) -> int:
        resultado = await self.session.execute(
            update(SesionUsuario)
            .where(SesionUsuario.actor_rol == rol, SesionUsuario.actor_id == actor_id,
                   SesionUsuario.fecha_cierre.is_(None), SesionUsuario.fecha_expiracion > ahora)
            .values(fecha_cierre=ahora, motivo_cierre=motivo)
            .execution_options(synchronize_session=False)
        )
        return int(resultado.rowcount or 0)
