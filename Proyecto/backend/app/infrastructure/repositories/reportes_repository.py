"""Adaptador de `ReportesPort`: lecturas de resumen, benchmark y comparativa (A-41)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.benchmark import Benchmark
from app.domain.models.dominio import Dominio
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.repositories.benchmark_repository import BenchmarkRepository


class ReportesRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def resumenes_con_dominio(self, evaluacion_id: int) -> list[tuple[Resumen, Dominio]]:
        result = await self.session.execute(
            select(Resumen, Dominio)
            .join(Dominio, Resumen.dominio_id == Dominio.id)
            .where(Resumen.evaluacion_id == evaluacion_id)
        )
        return list(result.all())

    async def benchmark_con_rubro_y_dominio(self, rubro_id: int | None
                                            ) -> list[tuple[Benchmark, Rubro, Dominio | None]]:
        query = (
            select(Benchmark, Rubro, Dominio)
            .join(Rubro, Benchmark.rubro_id == Rubro.id)
            .outerjoin(Dominio, Benchmark.dominio_id == Dominio.id)
            .order_by(Rubro.nombre_rubro, Benchmark.dominio_id.is_not(None), Dominio.nombre_dominio)
        )
        if rubro_id is not None:
            query = query.where(Benchmark.rubro_id == rubro_id)
        return list((await self.session.execute(query)).all())

    async def obtener_evaluacion(self, evaluacion_id: int) -> Evaluacion | None:
        return await self.session.get(Evaluacion, evaluacion_id)

    async def evaluacion_tiene_empresa(self, evaluacion_id: int) -> bool:
        return (await self.session.scalar(
            select(Evaluacion.empresa_id).where(Evaluacion.id == evaluacion_id)
        )) is not None

    async def rubro_id_de_evaluacion(self, evaluacion: Evaluacion) -> int | None:
        """El rubro de la empresa manda; si no, el del usuario temporal."""
        if evaluacion.empresa_id is not None:
            rubro = await self.session.scalar(select(Empresa.rubro_id).where(Empresa.id == evaluacion.empresa_id))
            if rubro is not None:
                return rubro
        if evaluacion.usuario_temporal_id is not None:
            return await self.session.scalar(
                select(UsuarioTemporal.rubro_id).where(UsuarioTemporal.id == evaluacion.usuario_temporal_id)
            )
        return None

    async def obtener_rubro(self, rubro_id: int) -> Rubro | None:
        return await self.session.get(Rubro, rubro_id)

    async def benchmark_del_rubro(self, rubro_id: int | None) -> dict[int | None, Benchmark]:
        """{dominio_id: fila}; la clave None es el puntaje general del rubro."""
        if rubro_id is None:
            return {}
        filas = await BenchmarkRepository(self.session).filas_del_rubro(rubro_id)
        return {b.dominio_id: b for b in filas}
