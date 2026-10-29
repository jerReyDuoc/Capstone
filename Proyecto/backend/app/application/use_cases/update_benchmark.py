from collections import defaultdict
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes.historial import evaluaciones_para_benchmark, mediana
from app.domain.models.benchmark import Benchmark
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.usuario_temporal import UsuarioTemporal


class UpdateBenchmarkUseCase:
    """
    Recalcula completamente la tabla benchmark (cron diario de ARQ y al completar).

    Qué evaluaciones cuentan:
      - completadas y no marcadas de prueba (HU-19);
      - HU-29: de cada empresa cliente, SOLO la más reciente (una empresa que se reevalúa
        varias veces no pesa más en el promedio de su rubro). Las evaluaciones sin
        empresa (encuestados anónimos) cuentan cada una.
    El rubro es el de la empresa y, si la evaluación no tiene empresa, el que eligió el
    usuario temporal (HU-29: la reevaluación no tiene usuario temporal).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self) -> dict:
        # 1. Candidatas: (evaluación, empresa, rubro)
        rubro = func.coalesce(Empresa.rubro_id, UsuarioTemporal.rubro_id)
        candidatas = (await self.session.execute(
            select(Evaluacion.id, Evaluacion.empresa_id, rubro.label("rubro_id"))
            .outerjoin(UsuarioTemporal, Evaluacion.usuario_temporal_id == UsuarioTemporal.id)
            .outerjoin(Empresa, Evaluacion.empresa_id == Empresa.id)
            .where(Evaluacion.estado_progreso == "completada")
            .where(Evaluacion.es_prueba.is_(False))  # HU-19: sin evaluaciones de prueba
        )).all()
        # La más reciente de cada empresa se elige ANTES de mirar el rubro: si la última no
        # tuviera rubro, no se cuenta una anterior en su lugar.
        cuentan = evaluaciones_para_benchmark((ev_id, empresa_id) for ev_id, empresa_id, _ in candidatas)
        rubro_de = {ev_id: rubro_id for ev_id, _, rubro_id in candidatas
                    if ev_id in cuentan and rubro_id is not None}

        # 2. Puntajes por rubro × dominio
        grupos: dict[tuple[int, int], list[float | None]] = defaultdict(list)
        if rubro_de:
            filas = (await self.session.execute(
                select(Resumen.evaluacion_id, Resumen.dominio_id, Resumen.puntaje_obtenido)
                .where(Resumen.evaluacion_id.in_(list(rubro_de)))
            )).all()
            for ev_id, dominio_id, puntaje in filas:
                grupos[(rubro_de[ev_id], dominio_id)].append(puntaje)

        # 3. Reemplazar la tabla (recalculamos todo)
        await self.session.execute(delete(Benchmark))
        creados = 0
        for (rubro_id, dominio_id), puntajes in sorted(grupos.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
            validos = [p for p in puntajes if p is not None]
            if not validos:
                continue
            self.session.add(Benchmark(
                rubro_id=rubro_id,
                dominio_id=dominio_id,
                promedio_puntaje=round(sum(validos) / len(validos), 2),
                mediana_puntaje=round(mediana(validos), 2),
                puntaje_maximo=round(max(validos), 2),
                puntaje_minimo=round(min(validos), 2),
                total_evaluaciones=len(puntajes),
            ))
            creados += 1

        await self.session.commit()

        return {
            "fecha_calculo": date.today().isoformat(),
            "total_benchmarks": creados,
            "total_evaluaciones_procesadas": len(rubro_de),
        }
