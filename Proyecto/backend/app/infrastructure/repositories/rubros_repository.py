"""Repositorio del catálogo de rubros para el mantenedor del admin."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.empresa import Empresa
from app.domain.models.rubro import Rubro
from app.domain.models.usuario_temporal import UsuarioTemporal


class RubrosRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def conteo_evaluaciones_por_rubro(self) -> dict[int, int]:
        return dict((await self.session.execute(
            select(UsuarioTemporal.rubro_id, func.count()).where(UsuarioTemporal.rubro_id.is_not(None))
            .group_by(UsuarioTemporal.rubro_id))).all())

    async def conteo_empresas_por_rubro(self) -> dict[int, int]:
        return dict((await self.session.execute(
            select(Empresa.rubro_id, func.count()).group_by(Empresa.rubro_id))).all())

    async def listar(self) -> list[Rubro]:
        return list((await self.session.execute(select(Rubro).order_by(Rubro.id))).scalars().all())

    async def obtener(self, rubro_id: int) -> Rubro | None:
        return await self.session.get(Rubro, rubro_id)

    async def existe_nombre(self, nombre: str, excepto: int | None = None) -> bool:
        q = select(Rubro.id).where(func.lower(func.trim(Rubro.nombre_rubro)) == nombre.lower())
        if excepto is not None:
            q = q.where(Rubro.id != excepto)
        return (await self.session.scalar(q.limit(1))) is not None

    async def intentar_agregar(self, nombre: str) -> Rubro | None:
        nuevo_id = int(await self.session.scalar(select(func.coalesce(func.max(Rubro.id), 0))) or 0) + 1
        rubro = Rubro(id=nuevo_id, nombre_rubro=nombre)
        self.session.add(rubro)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            return None
        return rubro
