"""HU-34 · Consultas y escrituras del mapa de datos (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errores import ConflictoIntegridadError
from app.domain.models.mapa_datos_tablas import MapaDatos, MapaDatosVersion, MapaElemento, MapaFlujo
from app.domain.models.pregunta_filtro import PreguntaFiltro
from app.domain.models.respuesta_filtro import RespuestaFiltro
from app.domain.models.rubro import Rubro


class MapaDatosRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def mapa(self, empresa_id: int, *, bloquear: bool = False) -> Any | None:
        q = select(MapaDatos).where(MapaDatos.empresa_id == empresa_id)
        if bloquear:
            q = q.with_for_update()
        return (await self.session.execute(q)).scalar_one_or_none()

    async def elementos(self, mapa_id: int) -> list:
        return list((await self.session.execute(
            select(MapaElemento).where(MapaElemento.mapa_id == mapa_id).order_by(MapaElemento.id))).scalars().all())

    async def flujos(self, mapa_id: int) -> list:
        return list((await self.session.execute(
            select(MapaFlujo).where(MapaFlujo.mapa_id == mapa_id).order_by(MapaFlujo.id))).scalars().all())

    async def nombre_rubro(self, rubro_id: int) -> str | None:
        return (await self.session.execute(select(Rubro.nombre_rubro).where(Rubro.id == rubro_id))).scalar_one_or_none()

    async def versiones_recientes(self, mapa_id: int, cuantos: int) -> list[tuple]:
        return list((await self.session.execute(
            select(MapaDatosVersion.numero, MapaDatosVersion.fecha, MapaDatosVersion.resumen)
            .where(MapaDatosVersion.mapa_id == mapa_id).order_by(MapaDatosVersion.numero.desc()).limit(cuantos))).all())

    async def contar_versiones(self, mapa_id: int) -> int:
        return (await self.session.execute(select(func.count()).select_from(MapaDatosVersion)
                                           .where(MapaDatosVersion.mapa_id == mapa_id))).scalar_one()

    async def pagina_de_versiones(self, mapa_id: int, desplazamiento: int, limite: int) -> list:
        return list((await self.session.execute(
            select(MapaDatosVersion).where(MapaDatosVersion.mapa_id == mapa_id)
            .order_by(MapaDatosVersion.numero.desc())
            .offset(desplazamiento).limit(limite))).scalars().all())

    async def version(self, mapa_id: int, numero: int) -> Any | None:
        return (await self.session.execute(select(MapaDatosVersion).where(
            MapaDatosVersion.mapa_id == mapa_id, MapaDatosVersion.numero == numero))).scalar_one_or_none()

    async def respuestas_filtro(self, evaluacion_id: int) -> list[tuple]:
        return list((await self.session.execute(
            select(PreguntaFiltro.codigo, RespuestaFiltro.respuesta)
            .join(RespuestaFiltro, RespuestaFiltro.pregunta_id == PreguntaFiltro.id_pregunta)
            .where(RespuestaFiltro.evaluacion_id == evaluacion_id))).all())

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)

    def agregar_varios(self, entidades: list) -> None:
        self.session.add_all(entidades)

    async def eliminar(self, entidad: Any) -> None:
        await self.session.delete(entidad)

    async def eliminar_flujos(self, ids: list[int]) -> None:
        await self.session.execute(delete(MapaFlujo).where(MapaFlujo.id.in_(ids))
                                   .execution_options(synchronize_session="fetch"))

    async def volcar(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError as e:
            raise ConflictoIntegridadError(str(e)) from e
