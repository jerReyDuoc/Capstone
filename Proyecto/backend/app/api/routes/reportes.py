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
from app.application.benchmark.k_anonimato import SUPRIMIDA, diferencia, posicion
from app.application.benchmark.sector import bloque_sector, filas_del_rubro, publicar_fila

GENERAL = "Puntaje general"

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
    Promedios agregados por rubro (HU-10, criterio 1): una fila por dimensión y una con
    `dominio_id = null` para el puntaje GENERAL del rubro.

    HU-10 (criterio 2): las filas cuya cohorte tiene menos de K_ANONIMATO_MINIMO empresas
    salen con `cohorte_suficiente = false` y TODAS sus métricas en null, incluido el número de
    empresas. Mediana y percentiles solo con K_ANONIMATO_DISTRIBUCION empresas o más. Máximo y
    mínimo ya no se publican: siempre son el puntaje de una sola empresa.

    HU-20: datos agregados (sin evaluaciones individuales), pero es un reporte: exige el
    token de un encuestado, referente o admin.
    """
    query = (
        select(Benchmark, Rubro, Dominio)
        .join(Rubro, Benchmark.rubro_id == Rubro.id)
        .outerjoin(Dominio, Benchmark.dominio_id == Dominio.id)
        .order_by(Rubro.nombre_rubro, Benchmark.dominio_id.is_not(None), Dominio.nombre_dominio)
    )
    if rubro_id is not None:
        query = query.where(Benchmark.rubro_id == rubro_id)

    filas = list((await db.execute(query)).all())
    return [
        {
            "rubro_id": rubro.id,
            "rubro": rubro.nombre_rubro,
            "dominio_id": dominio.id if dominio else None,
            "dominio": dominio.nombre_dominio if dominio else GENERAL,
            "k_minimo": settings.K_ANONIMATO_MINIMO,
            **publicar_fila(bm).como_dict(),
        }
        for bm, rubro, dominio in filas
    ]


@router.get("/{evaluacion_id}/comparativa", dependencies=[Depends(alcance_evaluacion)])
async def get_comparativa(evaluacion_id: int, db: AsyncSession = Depends(get_db)):
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
    evaluacion = await db.get(Evaluacion, evaluacion_id)
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    # HU-29: el rubro de la empresa (la reevaluación no tiene usuario temporal)
    from app.application.use_cases.historial_empresa import rubro_id_de_evaluacion

    rubro_id = await rubro_id_de_evaluacion(db, evaluacion)
    rubro = await db.get(Rubro, rubro_id) if rubro_id is not None else None

    resumenes = list((await db.execute(
        select(Resumen, Dominio)
        .join(Dominio, Resumen.dominio_id == Dominio.id)
        .where(Resumen.evaluacion_id == evaluacion_id)
    )).all())
    if not resumenes:
        raise HTTPException(status_code=404, detail="Genera el resumen primero con POST /cerrar")

    bench = await filas_del_rubro(db, rubro_id)
    general = publicar_fila(bench.get(None)) if rubro_id is not None else SUPRIMIDA

    meta = settings.META_CUMPLIMIENTO_PUNTAJE
    comparativas = []
    suma = controles = 0.0
    for resumen, dominio in sorted(resumenes, key=lambda rd: rd[1].nombre_dominio or ""):
        puntaje = resumen.puntaje_obtenido
        # Si el rubro completo está suprimido, ninguna dimensión se publica (coherencia)
        pub = publicar_fila(bench.get(dominio.id)) if general.suficiente else SUPRIMIDA
        if puntaje is not None and resumen.total_controles_evaluados:
            suma += puntaje * resumen.total_controles_evaluados
            controles += resumen.total_controles_evaluados
        comparativas.append({
            "dominio_id": dominio.id,
            "dominio": dominio.nombre_dominio,
            "tu_puntaje": puntaje,
            "tu_nivel": resumen.nivel_madurez,
            "promedio_industria": pub.promedio,
            "mediana_industria": pub.mediana,
            "percentil_25": pub.p25,
            "percentil_75": pub.p75,
            "cohorte_suficiente": pub.suficiente,
            "referencia_suficiente": pub.suficiente,  # nombre previo (HU-12)
            "empresas": pub.empresas,
            "muestras": pub.empresas,                 # nombre previo; null si la cohorte es < k
            "diferencia_vs_promedio": diferencia(puntaje, pub),
            "posicion": posicion(puntaje, pub),
            "meta": meta,
            "diferencia_vs_meta": round((puntaje or 0) - meta, 2),
            "cumple_meta": (puntaje or 0) >= meta,
        })

    tu_general = round(suma / controles, 2) if controles else None
    suprimidas = sum(1 for c in comparativas if not c["cohorte_suficiente"])
    return {
        "evaluacion_id": evaluacion_id,
        "rubro_id": rubro_id,
        "meta_puntaje": meta,
        "meta_nivel": nivel_madurez(meta),
        "k_minimo": settings.K_ANONIMATO_MINIMO,
        "muestras_minimas": settings.K_ANONIMATO_MINIMO,  # nombre previo (HU-12)
        "sector": bloque_sector(rubro_id, rubro.nombre_rubro if rubro else None, bench.get(None),
                                tu_general, suprimidas, len(comparativas)),
        "comparativas": comparativas,
    }
