"""HU-36 · Consultas del informe RAT y de la marca de revisión (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.documento_empresa import DocumentoEmpresa
from app.domain.models.empresa import Empresa
from app.domain.models.rat_informe import RatInforme
from app.domain.models.rat_modelo import RatActividad, RatActividadVersion
from app.domain.models.rat_revision import REVISADA, RatRevision
from app.domain.models.rubro import Rubro
from app.domain.rat import catalogo as cat


class InformeRatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def nombre_rubro(self, rubro_id: int) -> str | None:
        return (await self.session.execute(select(Rubro.nombre_rubro).where(Rubro.id == rubro_id))).scalar_one_or_none()

    async def actividades_no_archivadas(self, empresa_id: int) -> list:
        return list((await self.session.execute(
            select(RatActividad).where(RatActividad.empresa_id == empresa_id, RatActividad.estado != cat.ARCHIVADA)
            .order_by(RatActividad.nombre, RatActividad.id))).scalars().all())

    async def contar_archivadas(self, empresa_id: int) -> int:
        return (await self.session.execute(
            select(func.count()).select_from(RatActividad)
            .where(RatActividad.empresa_id == empresa_id, RatActividad.estado == cat.ARCHIVADA))).scalar() or 0

    async def versiones_de_actividades(self, actividad_ids: list[int]) -> list:
        return list((await self.session.execute(
            select(RatActividadVersion).where(RatActividadVersion.actividad_id.in_(actividad_ids)))).scalars())

    async def revision_revisada(self, empresa_id: int, *, revision_id: int | None = None,
                                huella: str | None = None) -> Any | None:
        q = select(RatRevision).where(RatRevision.empresa_id == empresa_id, RatRevision.estado == REVISADA)
        q = q.where(RatRevision.id == revision_id) if revision_id is not None else q.where(RatRevision.huella == huella)
        return (await self.session.execute(q.order_by(RatRevision.id.desc()).limit(1))).scalar_one_or_none()

    async def bloquear_empresa(self, empresa_id: int) -> None:
        await self.session.execute(select(Empresa.id).where(Empresa.id == empresa_id).with_for_update())

    async def ultima_emision(self, empresa_id: int) -> Any | None:
        q = (select(RatInforme).where(RatInforme.empresa_id == empresa_id)
             .order_by(RatInforme.id.desc()).limit(1))
        return (await self.session.execute(q)).scalar_one_or_none()

    async def emisiones_recientes(self, empresa_id: int, limite: int) -> list:
        return list((await self.session.execute(
            select(RatInforme).where(RatInforme.empresa_id == empresa_id)
            .order_by(RatInforme.id.desc()).limit(limite))).scalars().all())

    async def contar_emisiones_desde(self, empresa_id: int, desde: datetime) -> int:
        return (await self.session.execute(
            select(func.count()).select_from(RatInforme)
            .where(RatInforme.empresa_id == empresa_id, RatInforme.fecha >= desde))).scalar() or 0

    async def emision(self, informe_id: int) -> Any | None:
        return await self.session.get(RatInforme, informe_id)

    async def documento(self, documento_id: int) -> Any | None:
        return await self.session.get(DocumentoEmpresa, documento_id)

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)
