from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.benchmark import Benchmark
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.usuario_temporal import UsuarioTemporal


class UpdateBenchmarkUseCase:
    """
    Recalcula completamente la tabla benchmark.
    Se ejecuta diariamente vía cron de ARQ.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self) -> dict:
        # 1. Limpiar tabla actual (recalculamos todo)
        existing = await self.session.execute(select(Benchmark))
        for row in existing.scalars().all():
            await self.session.delete(row)
        await self.session.flush()

        # 2. Agrupar resúmenes de evaluaciones cerradas por rubro × dominio
        query = (
            select(
                UsuarioTemporal.rubro_id.label("rubro_id"),
                Resumen.dominio_id.label("dominio_id"),
                func.avg(Resumen.puntaje_obtenido).label("promedio"),
                func.max(Resumen.puntaje_obtenido).label("maximo"),
                func.min(Resumen.puntaje_obtenido).label("minimo"),
                func.count(Resumen.id_resumen).label("total"),
            )
            .join(Evaluacion, Resumen.evaluacion_id == Evaluacion.id)
            .join(UsuarioTemporal, Evaluacion.usuario_temporal_id == UsuarioTemporal.id)
            .where(Evaluacion.estado_progreso == "completada")
            .where(UsuarioTemporal.rubro_id.isnot(None))
            .group_by(UsuarioTemporal.rubro_id, Resumen.dominio_id)
        )

        result = await self.session.execute(query)
        filas = list(result.all())

        # 3. Calcular mediana por grupo (query aparte porque avg no da mediana)
        benchmarks_creados = 0
        for fila in filas:
            # Obtener todos los puntajes del grupo para calcular mediana
            puntajes_query = (
                select(Resumen.puntaje_obtenido)
                .join(Evaluacion, Resumen.evaluacion_id == Evaluacion.id)
                .join(UsuarioTemporal, Evaluacion.usuario_temporal_id == UsuarioTemporal.id)
                .where(Evaluacion.estado_progreso == "completada")
                .where(UsuarioTemporal.rubro_id == fila.rubro_id)
                .where(Resumen.dominio_id == fila.dominio_id)
            )
            puntajes_res = await self.session.execute(puntajes_query)
            puntajes = sorted([p for p in puntajes_res.scalars().all() if p is not None])

            if not puntajes:
                continue

            n = len(puntajes)
            if n % 2 == 0:
                mediana = (puntajes[n // 2 - 1] + puntajes[n // 2]) / 2
            else:
                mediana = puntajes[n // 2]

            benchmark = Benchmark(
                rubro_id=fila.rubro_id,
                dominio_id=fila.dominio_id,
                promedio_puntaje=round(fila.promedio or 0, 2),
                mediana_puntaje=round(mediana, 2),
                puntaje_maximo=round(fila.maximo or 0, 2),
                puntaje_minimo=round(fila.minimo or 0, 2),
                total_evaluaciones=fila.total or 0,
            )
            self.session.add(benchmark)
            benchmarks_creados += 1

        await self.session.commit()

        return {
            "fecha_calculo": date.today().isoformat(),
            "total_benchmarks": benchmarks_creados,
            "total_evaluaciones_procesadas": len(filas),
        }