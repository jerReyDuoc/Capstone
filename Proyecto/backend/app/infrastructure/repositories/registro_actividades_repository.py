"""HU-38 · Consultas del registro de actividades de tratamiento (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.mapa_datos_tablas import MapaDatos, MapaElemento, MapaFlujo
from app.domain.models.rat_modelo import RatActividad, RatActividadVersion
from app.domain.rat import catalogo as cat


class RegistroActividadesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---- mapa
    async def mapa(self, empresa_id: int) -> Any | None:
        return (await self.session.execute(select(MapaDatos).where(MapaDatos.empresa_id == empresa_id))) \
            .scalar_one_or_none()

    async def elementos_del_mapa(self, mapa_id: int) -> list:
        return list((await self.session.execute(select(MapaElemento).where(MapaElemento.mapa_id == mapa_id)
                                                .order_by(MapaElemento.id))).scalars().all())

    async def flujos_del_mapa(self, mapa_id: int) -> list:
        return list((await self.session.execute(select(MapaFlujo).where(MapaFlujo.mapa_id == mapa_id)
                                                .order_by(MapaFlujo.id))).scalars().all())

    # ---- actividades
    async def actividades_no_archivadas_bloqueadas(self, empresa_id: int) -> list:
        return list((await self.session.execute(
            select(RatActividad).where(RatActividad.empresa_id == empresa_id, RatActividad.estado != cat.ARCHIVADA)
            .order_by(RatActividad.id).with_for_update())).scalars().all())

    async def actividad(self, actividad_id: int, empresa_id: int, *, bloquear: bool = False) -> Any | None:
        q = select(RatActividad).where(RatActividad.id == actividad_id, RatActividad.empresa_id == empresa_id)
        if bloquear:
            q = q.with_for_update()
        return (await self.session.execute(q)).scalar_one_or_none()

    async def actividades(self, empresa_id: int) -> list:
        return list((await self.session.execute(
            select(RatActividad).where(RatActividad.empresa_id == empresa_id)
            .order_by(RatActividad.nombre))).scalars().all())

    async def contar_actividades(self, empresa_id: int) -> int:
        return (await self.session.execute(select(func.count()).select_from(RatActividad)
                                           .where(RatActividad.empresa_id == empresa_id))).scalar() or 0

    async def nombre_en_uso(self, empresa_id: int, nombre: str, excepto: int | None = None) -> bool:
        q = select(RatActividad.id).where(RatActividad.empresa_id == empresa_id,
                                          func.lower(RatActividad.nombre) == nombre.lower())
        if excepto is not None:
            q = q.where(RatActividad.id != excepto)
        return (await self.session.execute(q.limit(1))).scalar_one_or_none() is not None

    # ---- versiones
    async def ultima_version(self, actividad_id: int) -> Any | None:
        return (await self.session.execute(
            select(RatActividadVersion).where(RatActividadVersion.actividad_id == actividad_id)
            .order_by(RatActividadVersion.numero.desc()).limit(1))).scalar_one_or_none()

    async def versiones(self, actividad_id: int) -> list:
        return list((await self.session.execute(
            select(RatActividadVersion).where(RatActividadVersion.actividad_id == actividad_id)
            .order_by(RatActividadVersion.numero.desc()))).scalars().all())

    async def version(self, actividad_id: int, numero: int) -> Any | None:
        return (await self.session.execute(
            select(RatActividadVersion).where(RatActividadVersion.actividad_id == actividad_id,
                                              RatActividadVersion.numero == numero))).scalar_one_or_none()

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)
