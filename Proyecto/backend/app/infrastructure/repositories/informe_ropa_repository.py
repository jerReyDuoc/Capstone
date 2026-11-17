"""HU-37 · Consultas y escrituras del informe RoPA de la empresa (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.documento_empresa import DocumentoEmpresa
from app.domain.models.empresa import Empresa
from app.domain.models.ropa_modelo import RopaDatos, RopaInforme


class InformeRopaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def datos(self, empresa_id: int) -> Any | None:
        return (await self.session.execute(
            select(RopaDatos).where(RopaDatos.empresa_id == empresa_id))).scalar_one_or_none()

    async def ultima_emision(self, empresa_id: int) -> Any | None:
        return (await self.session.execute(
            select(RopaInforme).where(RopaInforme.empresa_id == empresa_id)
            .order_by(RopaInforme.id.desc()).limit(1))).scalar_one_or_none()

    async def emisiones_recientes(self, empresa_id: int, limite: int) -> list:
        return list((await self.session.execute(
            select(RopaInforme).where(RopaInforme.empresa_id == empresa_id)
            .order_by(RopaInforme.id.desc()).limit(limite))).scalars().all())

    async def contar_desde(self, empresa_id: int, desde: datetime) -> int:
        return (await self.session.execute(
            select(func.count()).select_from(RopaInforme)
            .where(RopaInforme.empresa_id == empresa_id, RopaInforme.fecha >= desde))).scalar() or 0

    async def documento(self, documento_id: int) -> Any | None:
        return await self.session.get(DocumentoEmpresa, documento_id)

    async def emision(self, informe_id: int) -> Any | None:
        return await self.session.get(RopaInforme, informe_id)

    async def bloquear_empresa(self, empresa_id: int) -> None:
        await self.session.execute(select(Empresa.id).where(Empresa.id == empresa_id).with_for_update())

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)

    async def refrescar(self, entidad: Any) -> None:
        await self.session.refresh(entidad)
