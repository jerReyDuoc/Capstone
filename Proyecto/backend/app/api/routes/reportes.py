import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alcance import actor_de_evaluaciones, alcance_evaluacion
from app.core.autenticacion import Actor
from app.core.config import settings
from app.core.database import get_db
from app.application.use_cases.generate_resumen import GenerateResumenUseCase, nivel_madurez
from app.application.use_cases.completar_evaluacion import CompletarEvaluacionUseCase
from app.application.use_cases.create_respuesta import RespuestaRechazadaError
from app.domain.models.resumen import Resumen
from app.domain.models.dominio import Dominio
from app.domain.models.benchmark import Benchmark
from app.domain.models.rubro import Rubro
from app.domain.models.evaluacion import Evaluacion

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
                               actor: Actor | None = Depends(alcance_evaluacion)):
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
    if await db.scalar(select(Evaluacion.empresa_id).where(Evaluacion.id == evaluacion_id)) is not None:
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
    from app.application.use_cases.update_benchmark import UpdateBenchmarkUseCase

    try:
        await UpdateBenchmarkUseCase(db).execute()
    except Exception:  # noqa: BLE001
        await db.rollback()
        logger.exception("[benchmark] no se pudo recalcular al completar; lo hará el cron diario")


@router.get("/{evaluacion_id}/resumen", dependencies=[Depends(alcance_evaluacion)])
async def get_resumen(evaluacion_id: int, db: AsyncSession = Depends(get_db)):
    """Devuelve los resúmenes guardados por dominio + puntaje general."""
    result = await db.execute(
        select(Resumen, Dominio)
        .join(Dominio, Resumen.dominio_id == Dominio.id)
        .where(Resumen.evaluacion_id == evaluacion_id)
    )
    filas = list(result.all())

    if not filas:
        raise HTTPException(
            status_code=404,
            detail="No hay resumen generado. Llama a POST /cerrar primero."
        )

    dominios = []
    total_controles = 0
    suma_ponderada = 0.0

    for resumen, dominio in filas:
        dominios.append({
            "dominio_id": dominio.id,
            "dominio": dominio.nombre_dominio,
            "puntaje": resumen.puntaje_obtenido,
            "nivel_madurez": resumen.nivel_madurez,
            "total_controles_evaluados": resumen.total_controles_evaluados,
        })
        total_controles += resumen.total_controles_evaluados or 0
        suma_ponderada += (resumen.puntaje_obtenido or 0) * (resumen.total_controles_evaluados or 0)

    puntaje_general = round(suma_ponderada / total_controles, 2) if total_controles > 0 else 0.0

    return {
        "evaluacion_id": evaluacion_id,
        "puntaje_general": puntaje_general,
        "nivel_madurez_general": nivel_madurez(puntaje_general),
        "total_controles_evaluados": total_controles,
        "dominios": dominios,
    }

@router.get("/benchmark", dependencies=[Depends(actor_de_evaluaciones)])
async def get_benchmark(
    rubro_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve los promedios del mercado por rubro y dominio.
    Si no se especifica rubro_id, devuelve todos.

    HU-20: datos agregados (sin evaluaciones individuales), pero es un reporte: exige el
    token de un encuestado, referente o admin.
    """
    query = (
        select(Benchmark, Rubro, Dominio)
        .join(Rubro, Benchmark.rubro_id == Rubro.id)
        .join(Dominio, Benchmark.dominio_id == Dominio.id)
        .order_by(Rubro.nombre_rubro, Dominio.nombre_dominio)
    )
    if rubro_id is not None:
        query = query.where(Benchmark.rubro_id == rubro_id)

    result = await db.execute(query)
    filas = list(result.all())

    return [
        {
            "rubro_id": rubro.id,
            "rubro": rubro.nombre_rubro,
            "dominio_id": dominio.id,
            "dominio": dominio.nombre_dominio,
            "promedio": bm.promedio_puntaje,
            "mediana": bm.mediana_puntaje,
            "maximo": bm.puntaje_maximo,
            "minimo": bm.puntaje_minimo,
            "total_evaluaciones": bm.total_evaluaciones,
        }
        for bm, rubro, dominio in filas
    ]


@router.get("/{evaluacion_id}/comparativa", dependencies=[Depends(alcance_evaluacion)])
async def get_comparativa(evaluacion_id: int, db: AsyncSession = Depends(get_db)):
    """
    Compara el resumen de una evaluación con:
      - la META de cumplimiento (META_CUMPLIMIENTO_PUNTAJE): lo que debería alcanzar cada
        dimensión. Siempre está, aunque no haya benchmark ni rubro.
      - el promedio de su RUBRO (benchmark), solo si hay COMPARATIVA_MIN_MUESTRAS o más
        evaluaciones completadas; si no, promedio_industria = null y `muestras` dice cuántas hay.
    """
    evaluacion = await db.get(Evaluacion, evaluacion_id)
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    # HU-29: el rubro de la empresa (la reevaluación no tiene usuario temporal)
    from app.application.use_cases.historial_empresa import rubro_id_de_evaluacion

    rubro_id = await rubro_id_de_evaluacion(db, evaluacion)

    resumenes_result = await db.execute(
        select(Resumen, Dominio)
        .join(Dominio, Resumen.dominio_id == Dominio.id)
        .where(Resumen.evaluacion_id == evaluacion_id)
    )
    resumenes = list(resumenes_result.all())

    if not resumenes:
        raise HTTPException(status_code=404, detail="Genera el resumen primero con POST /cerrar")

    benchmarks = {}
    if rubro_id is not None:
        benchmarks_result = await db.execute(select(Benchmark).where(Benchmark.rubro_id == rubro_id))
        benchmarks = {b.dominio_id: b for b in benchmarks_result.scalars().all()}

    meta = settings.META_CUMPLIMIENTO_PUNTAJE
    minimo = settings.COMPARATIVA_MIN_MUESTRAS
    comparativas = []
    for resumen, dominio in resumenes:
        bm = benchmarks.get(dominio.id)
        muestras = (bm.total_evaluaciones or 0) if bm else 0
        suficiente = bm is not None and muestras >= minimo
        puntaje = resumen.puntaje_obtenido
        comparativas.append({
            "dominio": dominio.nombre_dominio,
            "tu_puntaje": puntaje,
            "tu_nivel": resumen.nivel_madurez,
            "promedio_industria": bm.promedio_puntaje if suficiente else None,
            "mediana_industria": bm.mediana_puntaje if suficiente else None,
            "maximo_industria": bm.puntaje_maximo if suficiente else None,
            "minimo_industria": bm.puntaje_minimo if suficiente else None,
            "muestras": muestras,
            "referencia_suficiente": suficiente,
            "diferencia_vs_promedio": round((puntaje or 0) - (bm.promedio_puntaje or 0), 2) if suficiente else None,
            "meta": meta,
            "diferencia_vs_meta": round((puntaje or 0) - meta, 2),
            "cumple_meta": (puntaje or 0) >= meta,
        })

    return {
        "evaluacion_id": evaluacion_id,
        "rubro_id": rubro_id,
        "meta_puntaje": meta,
        "meta_nivel": nivel_madurez(meta),
        "muestras_minimas": minimo,
        "comparativas": comparativas,
    }
