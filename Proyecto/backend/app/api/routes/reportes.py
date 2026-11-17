import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencias.alcance import actor_de_evaluaciones, alcance_evaluacion
from app.api.dependencias.consultas import reportes_evaluacion_uc
from app.domain.auth.actor import Actor
from app.core.config import settings
from app.core.database import get_db
from app.application.use_cases.generar_resumen import GenerateResumenUseCase
from app.application.use_cases.completar_evaluacion import CompletarEvaluacionUseCase
from app.application.use_cases.crear_respuesta import RespuestaRechazadaError
from app.application.use_cases.reportes_evaluacion import ReporteNoDisponibleError, ReportesEvaluacionUseCase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evaluaciones", tags=["reportes"])


@router.post("/{evaluacion_id}/cerrar", dependencies=[Depends(alcance_evaluacion)])
async def cerrar_evaluacion(evaluacion_id: int, db: AsyncSession = Depends(get_db)):
    """Genera los resúmenes por dominio y calcula el puntaje general."""
    use_case = GenerateResumenUseCase(db)
    try:
        return await use_case.execute(evaluacion_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/{evaluacion_id}/completar",
    responses={
        404: {"description": "Evaluación inexistente"},
        409: {"description": "Ya cerrada, filtro pendiente, cuestionario incompleto o evidencias en validación"},
    },
)
async def completar_evaluacion(evaluacion_id: int, db: AsyncSession = Depends(get_db),
                               actor: Actor | None = Depends(alcance_evaluacion),
                               uc: ReportesEvaluacionUseCase = Depends(reportes_evaluacion_uc)):
    """
    Cierre DEFINITIVO de la evaluación: exige el cuestionario completo y sin
    evidencias en validación, genera el resumen y marca `estado_progreso = completada`.
    Desde ahí no admite respuestas, cambios de filtro ni evidencias, y entra al
    benchmark. (`POST /cerrar` sigue siendo el recálculo/vista previa sin cerrar.)

    HU-29: si la evaluación es de una empresa cliente, el cierre queda en la bitácora y su
    informe PDF se archiva en "Mis documentos" (`documento_id`; null si no se pudo).
    """
    try:
        resultado = await CompletarEvaluacionUseCase(db).execute(evaluacion_id)
    except RespuestaRechazadaError as e:
        raise HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": str(e)})
    if await uc.evaluacion_tiene_empresa(evaluacion_id):
        from app.application.use_cases.documentos_empresa import tras_completar

        resultado = {**resultado, "documento_id": await tras_completar(db, evaluacion_id, actor)}
    if settings.BENCHMARK_AL_COMPLETAR:
        await _recalcular_benchmark(db)
    return resultado


async def _recalcular_benchmark(db: AsyncSession) -> None:
    """
    La comparativa con la industria sale de la tabla benchmark, que antes solo se
    recalculaba en el cron de las 02:00 UTC: quien completaba la encuesta no veía la
    comparativa hasta el día siguiente. Se recalcula al completar (la evaluación ya quedó
    completada y confirmada por el caso de uso) y, si falla, /completar responde igual:
    el cron diario lo repara.
    """
    from app.application.use_cases.actualizar_benchmark import UpdateBenchmarkUseCase

    try:
        await UpdateBenchmarkUseCase(db).execute()
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.exception("[benchmark] no se pudo recalcular al completar; lo hará el cron diario")


@router.get("/{evaluacion_id}/resumen", dependencies=[Depends(alcance_evaluacion)])
async def get_resumen(evaluacion_id: int, uc: ReportesEvaluacionUseCase = Depends(reportes_evaluacion_uc)):
    """Devuelve los resúmenes guardados por dominio + puntaje general."""
    try:
        return await uc.resumen(evaluacion_id)
    except ReporteNoDisponibleError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/benchmark", dependencies=[Depends(actor_de_evaluaciones)])
async def get_benchmark(
    rubro_id: int | None = None,
    uc: ReportesEvaluacionUseCase = Depends(reportes_evaluacion_uc),
):
    """
    Promedios agregados por rubro (HU-10, criterio 1): una fila por dimensión y una con
    `dominio_id = null` para el puntaje GENERAL del rubro.

    HU-10 (criterio 2): las filas cuya cohorte tiene menos de K_ANONIMATO_MINIMO empresas
    salen con `cohorte_suficiente = false` y TODAS sus métricas en null, incluido el número de
    empresas. Mediana y percentiles solo con K_ANONIMATO_DISTRIBUCION empresas o más. Máximo y
    mínimo ya no se publican: siempre son el puntaje de una sola empresa.

    HU-20: datos agregados (sin evaluaciones individuales), pero es un reporte: exige el
    token de un encuestado, referente o admin.
    """
    return await uc.benchmark(rubro_id)


@router.get("/{evaluacion_id}/comparativa", dependencies=[Depends(alcance_evaluacion)])
async def get_comparativa(evaluacion_id: int, uc: ReportesEvaluacionUseCase = Depends(reportes_evaluacion_uc)):
    """
    Compara el resumen de una evaluación con:
      - la META de cumplimiento (META_CUMPLIMIENTO_PUNTAJE): lo que debería alcanzar cada
        dimensión. Siempre está, aunque no haya benchmark ni rubro.
      - HU-10: su SECTOR (rubro). `sector` resume el puntaje general frente al rubro y trae
        la `advertencia` que la interfaz debe mostrar; cada fila de `comparativas` trae la
        dimensión. Si la cohorte tiene menos de K_ANONIMATO_MINIMO empresas, las métricas del
        sector salen en null (`cohorte_suficiente = false`) y no se revela cuántas hay.
        `posicion` dice en qué franja del sector queda la empresa sin mostrar puntajes ajenos.
    """
    try:
        return await uc.comparativa(evaluacion_id)
    except ReporteNoDisponibleError as e:
        raise HTTPException(status_code=404, detail=str(e))
