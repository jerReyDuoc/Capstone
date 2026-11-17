import logging
from collections import defaultdict
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.domain.benchmark.k_anonimato import FilaCandidata, calcular, evaluaciones_por_organizacion

logger = logging.getLogger(__name__)


class ActualizarBenchmarkUseCase:
    """
    Recalcula completamente la tabla benchmark (cron diario de ARQ y al completar).

    Qué evaluaciones cuentan:
      - completadas y no marcadas de prueba (HU-19);
      - HU-10 (antes HU-29): de cada ORGANIZACIÓN solo la más reciente. La organización es la
        empresa cliente; si la evaluación no tiene empresa, el usuario temporal del
        encuestado. Así una empresa que se reevalúa, o alguien que repite la encuesta, no
        pesa más en el promedio ni infla la cohorte k que decide la supresión.
    El rubro es el de la empresa y, si la evaluación no tiene empresa, el que eligió el
    usuario temporal (HU-29: la reevaluación no tiene usuario temporal).

    Por cada rubro guarda una fila por dimensión y (HU-10) una fila con dominio_id NULL con
    el puntaje GENERAL (promedio ponderado por controles, igual que GET /resumen).
    total_empresas = k. Estos valores son internos: se publican con k_anonimato.publicar().
    """
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = fabricas().recalculo_benchmark(session)

    async def execute(self) -> dict:
        # 1. Candidatas: (evaluación, empresa, usuario temporal, rubro)
        candidatas = await self.repo.candidatas()
        # La más reciente de cada organización se elige ANTES de mirar el rubro: si la última
        # no tuviera rubro, no se cuenta una anterior en su lugar.
        cuentan = evaluaciones_por_organizacion(
            FilaCandidata(ev_id, empresa_id, temporal_id) for ev_id, empresa_id, temporal_id, _ in candidatas
        )
        rubro_de = {ev_id: rubro_id for ev_id, _, _, rubro_id in candidatas
                    if ev_id in cuentan and rubro_id is not None}

        # 2. Puntajes por rubro × dominio, y el general de cada evaluación
        grupos: dict[tuple[int, int | None], list[float | None]] = defaultdict(list)
        ponderado: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])  # ev -> [suma, controles]
        if rubro_de:
            filas = await self.repo.resumenes(list(rubro_de))
            for ev_id, dominio_id, puntaje, controles in filas:
                grupos[(rubro_de[ev_id], dominio_id)].append(puntaje)
                if puntaje is not None and controles:
                    ponderado[ev_id][0] += puntaje * controles
                    ponderado[ev_id][1] += controles
            for ev_id, (suma, controles) in ponderado.items():
                if controles:
                    grupos[(rubro_de[ev_id], None)].append(suma / controles)

        # 3. Reemplazar la tabla (recalculamos todo)
        nuevas: list[dict] = []
        for (rubro_id, dominio_id), puntajes in sorted(grupos.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
            e = calcular(puntajes)
            if not e.empresas:
                continue
            nuevas.append(dict(
                rubro_id=rubro_id,
                dominio_id=dominio_id,
                promedio_puntaje=e.promedio,
                mediana_puntaje=e.mediana,
                puntaje_maximo=e.maximo,
                puntaje_minimo=e.minimo,
                total_evaluaciones=len(puntajes),
                total_empresas=e.empresas,
                percentil_25=e.p25,
                percentil_75=e.p75,
            ))
        await self.repo.reemplazar(nuevas)
        creados = len(nuevas)

        await self.session.commit()

        return {
            "fecha_calculo": date.today().isoformat(),
            "total_benchmarks": creados,
            "total_evaluaciones_procesadas": len(rubro_de),
        }

    async def recalcular_sin_fallar(self) -> None:
        """Recalcula al completar una evaluación; si falla, rollback y log: el cron diario lo repara."""
        try:
            await self.execute()
        except Exception:  # noqa: BLE001
            await self.session.rollback()
            logger.exception("[benchmark] no se pudo recalcular al completar; lo hará el cron diario")
