from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.dominio import Dominio
from app.domain.models.rubro import Rubro
from app.domain.models.ruta_formativa import RutaFormativa
from app.domain.models.catalogo_brechas import CatalogoBrechas
from app.domain.models.matriz_control import MatrizControl


class CatalogoRepository:
    """Repositorio de solo lectura para los catálogos maestros.

    HU-24: las rutas y brechas retiradas en una versión de la matriz (activo=false) no se
    listan; siguen en la BD para las evaluaciones anteriores."""

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
            select(RutaFormativa).where(RutaFormativa.activo.is_(True)).order_by(RutaFormativa.id)
        )
        return list(result.scalars().all())

    async def list_brechas(self) -> list[CatalogoBrechas]:
        result = await self.session.execute(
            select(CatalogoBrechas)
            .options(selectinload(CatalogoBrechas.ruta_formativa_rel))
            .where(CatalogoBrechas.activo.is_(True))
            .order_by(CatalogoBrechas.id_brecha)
        )
        return list(result.scalars().all())

    async def list_controles(self, dominio_id: int | None = None, criticidad: str | None = None) -> list[MatrizControl]:
        # HU-24: los retirados en una versión de la matriz no se listan (se conservan en la BD)
        query = select(MatrizControl).where(MatrizControl.activo.is_(True)).order_by(MatrizControl.id_control)
        if dominio_id is not None:
            query = query.where(MatrizControl.dominio_id == dominio_id)
        if criticidad is not None:
            query = query.where(MatrizControl.criticidad == criticidad)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_control(self, control_id: int) -> MatrizControl | None:
        result = await self.session.execute(select(MatrizControl).where(MatrizControl.id_control == control_id))
        return result.scalar_one_or_none()
