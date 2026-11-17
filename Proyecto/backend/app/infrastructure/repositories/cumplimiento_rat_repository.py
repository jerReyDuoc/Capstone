"""HU-38 · Consultas del cruce del registro con la evaluación (extraídas del caso de uso, A-12)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.evaluacion import Evaluacion
from app.domain.models.formacion_recorrido import AvanceFormativo
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.rat_modelo import RatActividad
from app.domain.models.respuesta import Respuesta
from app.domain.rat import catalogo as cat


class CumplimientoRatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def actividades_no_archivadas(self, empresa_id: int) -> list:
        return list((await self.session.execute(
            select(RatActividad).where(RatActividad.empresa_id == empresa_id, RatActividad.estado != cat.ARCHIVADA)
            .order_by(RatActividad.nombre, RatActividad.id))).scalars().all())

    async def evaluacion(self, evaluacion_id: int) -> Any | None:
        return await self.session.get(Evaluacion, evaluacion_id)

    async def controles_por_codigo(self, codigos: list[str]) -> list:
        return list((await self.session.execute(
            select(MatrizControl).where(MatrizControl.codigo_control.in_(sorted(set(codigos))))
            .order_by(MatrizControl.id_control))).scalars().all())

    async def respuestas_con_control(self, evaluacion_id: int, codigos: list[str]) -> list[tuple[Any, Any]]:
        filas = (await self.session.execute(
            select(Respuesta, MatrizControl)
            .join(MatrizControl, MatrizControl.id_control == Respuesta.matriz_controles_id_control)
            .where(Respuesta.evaluacion_id == evaluacion_id, MatrizControl.codigo_control.in_(sorted(set(codigos))))
            .order_by(Respuesta.id))).all()
        return [(r, c) for r, c in filas]

    async def avances_formativos(self, empresa_id: int, ruta_ids: list[int]) -> list:
        return list((await self.session.execute(
            select(AvanceFormativo).where(AvanceFormativo.empresa_id == empresa_id,
                                          AvanceFormativo.ruta_formativa_id.in_(ruta_ids))
        )).scalars().all())

    def agregar(self, entidad: Any) -> None:
        self.session.add(entidad)
