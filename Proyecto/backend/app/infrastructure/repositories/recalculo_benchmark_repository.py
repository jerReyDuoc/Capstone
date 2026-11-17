"""Lecturas y reemplazo de la tabla benchmark para el recálculo (cron diario y al completar)."""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.benchmark import Benchmark
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.usuario_temporal import UsuarioTemporal


class RecalculoBenchmarkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def candidatas(self) -> list[tuple[int, int | None, int | None, int | None]]:
        rubro = func.coalesce(Empresa.rubro_id, UsuarioTemporal.rubro_id)
        filas = (await self.session.execute(
            select(Evaluacion.id, Evaluacion.empresa_id, Evaluacion.usuario_temporal_id, rubro.label("rubro_id"))
            .outerjoin(UsuarioTemporal, Evaluacion.usuario_temporal_id == UsuarioTemporal.id)
            .outerjoin(Empresa, Evaluacion.empresa_id == Empresa.id)
            .where(Evaluacion.estado_progreso == "completada")
            .where(Evaluacion.es_prueba.is_(False))  # HU-19: sin evaluaciones de prueba
        )).all()
        return [tuple(f) for f in filas]

    async def resumenes(self, evaluacion_ids: list[int]) -> list[tuple[int, int | None, float | None, int | None]]:
        filas = (await self.session.execute(
            select(Resumen.evaluacion_id, Resumen.dominio_id, Resumen.puntaje_obtenido,
                   Resumen.total_controles_evaluados)
            .where(Resumen.evaluacion_id.in_(evaluacion_ids))
        )).all()
        return [tuple(f) for f in filas]

    async def reemplazar(self, filas: list[dict]) -> None:
        await self.session.execute(delete(Benchmark))
        for datos in filas:
            self.session.add(Benchmark(**datos))
