from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.dominio import Dominio
from app.domain.models.rubro import Rubro
from app.domain.models.ruta_formativa import RutaFormativa
from app.domain.models.catalogo_brechas import CatalogoBrechas


class CatalogoRepository:
    """Repositorio de solo lectura para los catálogos maestros."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_dominios(self) -> list[Dominio]:
        result = await self.session.execute(
            select(Dominio).order_by(Dominio.id)
        )
        return list(result.scalars().all())

    async def list_rubros(self) -> list[Rubro]:
        result = await self.session.execute(
            select(Rubro).order_by(Rubro.id)
        )
        return list(result.scalars().all())

    async def list_rutas_formativas(self) -> list[RutaFormativa]:
        result = await self.session.execute(
            select(RutaFormativa).order_by(RutaFormativa.id)
        )
        return list(result.scalars().all())

    async def list_brechas(self) -> list[CatalogoBrechas]:
        result = await self.session.execute(
            select(CatalogoBrechas)
            .options(selectinload(CatalogoBrechas.ruta_formativa_rel))
            .order_by(CatalogoBrechas.id_brecha)
        )
        return list(result.scalars().all())