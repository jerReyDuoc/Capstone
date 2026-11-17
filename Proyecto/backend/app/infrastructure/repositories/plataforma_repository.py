"""HU-41 · Consultas y escrituras de los informes de privacidad de la plataforma (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.plataforma import ID_REGISTRO, PlataformaInforme, PlataformaRegistro


class PlataformaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def datos(self) -> Any | None:
        return await self.session.get(PlataformaRegistro, ID_REGISTRO)

    async def ultima_emision(self, tipo: str) -> Any | None:
        q = (select(PlataformaInforme).where(PlataformaInforme.tipo == tipo, PlataformaInforme.codigo.is_not(None))
             .order_by(PlataformaInforme.id.desc()).limit(1))
        return (await self.session.execute(q)).scalar_one_or_none()

    async def emisiones_recientes(self, limite: int) -> list:
        return list((await self.session.execute(
            select(PlataformaInforme).where(PlataformaInforme.codigo.is_not(None))
            .order_by(PlataformaInforme.id.desc()).limit(limite))).scalars().all())

    async def contar_desde(self, desde: datetime) -> int:
        return (await self.session.execute(
            select(func.count()).select_from(PlataformaInforme)
            .where(PlataformaInforme.fecha >= desde))).scalar() or 0

    async def emision(self, informe_id: int) -> Any | None:
        return await self.session.get(PlataformaInforme, informe_id)

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)

    async def refrescar(self, entidad: Any) -> None:
        await self.session.refresh(entidad)
