"""Repositorio del avance formativo de la empresa cliente (HU-26)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.dominio import Dominio
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.formacion_recorrido import AvanceFormativo, LeccionFormativa, PreguntaVerificacion
from app.domain.models.ruta_formativa import RutaFormativa


class FormacionEmpresaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return await self.session.get(Evaluacion, evaluacion_id)

    async def avances_de_empresa(self, empresa_id: int) -> list[AvanceFormativo]:
        filas = (await self.session.execute(
            select(AvanceFormativo).where(AvanceFormativo.empresa_id == empresa_id)
        )).scalars().all()
        return list(filas)

    async def lecciones_de_ruta(self, ruta_id: int) -> list[LeccionFormativa]:
        filas = (await self.session.execute(
            select(LeccionFormativa).where(LeccionFormativa.ruta_formativa_id == ruta_id)
        )).scalars().all()
        return list(filas)

    async def orden_de_todas_las_lecciones(self) -> list[tuple[int, int]]:
        filas = (await self.session.execute(
            select(LeccionFormativa.ruta_formativa_id, LeccionFormativa.orden)
        )).all()
        return [(ruta_id, orden) for ruta_id, orden in filas]

    async def preguntas_de_ruta(self, ruta_id: int) -> list[PreguntaVerificacion]:
        filas = (await self.session.execute(
            select(PreguntaVerificacion).where(PreguntaVerificacion.ruta_formativa_id == ruta_id)
        )).scalars().all()
        return list(filas)

    async def avance_para_actualizar(self, empresa_id: int, ruta_id: int) -> AvanceFormativo | None:
        return (await self.session.execute(
            select(AvanceFormativo).where(
                AvanceFormativo.empresa_id == empresa_id, AvanceFormativo.ruta_formativa_id == ruta_id
            ).with_for_update()
        )).scalar_one_or_none()

    async def obtener_avance(self, empresa_id: int, ruta_id: int) -> AvanceFormativo | None:
        return (await self.session.execute(
            select(AvanceFormativo).where(
                AvanceFormativo.empresa_id == empresa_id, AvanceFormativo.ruta_formativa_id == ruta_id
            )
        )).scalar_one_or_none()

    def agregar_avance(self, avance: AvanceFormativo) -> None:
        self.session.add(avance)

    async def obtener_ruta(self, ruta_id: int) -> RutaFormativa | None:
        return await self.session.get(RutaFormativa, ruta_id)

    async def obtener_dominio(self, dominio_id: int) -> Dominio | None:
        return await self.session.get(Dominio, dominio_id)
