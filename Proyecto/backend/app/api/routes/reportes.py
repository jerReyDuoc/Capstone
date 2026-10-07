from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.application.use_cases.generate_resumen import GenerateResumenUseCase
from app.domain.models.resumen import Resumen
from app.domain.models.dominio import Dominio
from app.domain.models.benchmark import Benchmark
from app.domain.models.rubro import Rubro

router = APIRouter(prefix="/api/evaluaciones", tags=["reportes"])


@router.post("/{evaluacion_id}/cerrar")
async def cerrar_evaluacion(evaluacion_id: int, db: AsyncSession = Depends(get_db)):
    """Genera los resúmenes por dominio y calcula el puntaje general."""
    use_case = GenerateResumenUseCase(db)
    try:
        return await use_case.execute(evaluacion_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{evaluacion_id}/resumen")
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

    from app.application.use_cases.generate_resumen import nivel_madurez

    return {
        "evaluacion_id": evaluacion_id,
        "puntaje_general": puntaje_general,
        "nivel_madurez_general": nivel_madurez(puntaje_general),
        "total_controles_evaluados": total_controles,
        "dominios": dominios,
    }

@router.get("/benchmark")
async def get_benchmark(
    rubro_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve los promedios del mercado por rubro y dominio.
    Si no se especifica rubro_id, devuelve todos.
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


@router.get("/{evaluacion_id}/comparativa")
async def get_comparativa(evaluacion_id: int, db: AsyncSession = Depends(get_db)):
    """
    Compara el resumen de una evaluación contra el benchmark de su rubro.
    """
    # 1. Obtener la evaluación y su rubro
    evaluacion = await db.get(Evaluacion, evaluacion_id)
    if not evaluacion or not evaluacion.usuario_temporal_id:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    usuario = await db.get(UsuarioTemporal, evaluacion.usuario_temporal_id)
    if not usuario or not usuario.rubro_id:
        raise HTTPException(status_code=400, detail="La evaluación no tiene rubro asociado")

    # 2. Obtener resúmenes de la evaluación
    resumenes_result = await db.execute(
        select(Resumen, Dominio)
        .join(Dominio, Resumen.dominio_id == Dominio.id)
        .where(Resumen.evaluacion_id == evaluacion_id)
    )
    resumenes = list(resumenes_result.all())

    if not resumenes:
        raise HTTPException(status_code=404, detail="Genera el resumen primero con POST /cerrar")

    # 3. Obtener benchmarks del rubro
    benchmarks_result = await db.execute(
        select(Benchmark).where(Benchmark.rubro_id == usuario.rubro_id)
    )
    benchmarks = {b.dominio_id: b for b in benchmarks_result.scalars().all()}

    # 4. Combinar
    comparativas = []
    for resumen, dominio in resumenes:
        bm = benchmarks.get(dominio.id)
        comparativas.append({
            "dominio": dominio.nombre_dominio,
            "tu_puntaje": resumen.puntaje_obtenido,
            "tu_nivel": resumen.nivel_madurez,
            "promedio_industria": bm.promedio_puntaje if bm else None,
            "mediana_industria": bm.mediana_puntaje if bm else None,
            "maximo_industria": bm.puntaje_maximo if bm else None,
            "minimo_industria": bm.puntaje_minimo if bm else None,
            "muestras": bm.total_evaluaciones if bm else 0,
            "diferencia_vs_promedio": round(
                (resumen.puntaje_obtenido or 0) - (bm.promedio_puntaje or 0), 2
            ) if bm else None,
        })

    return {
        "evaluacion_id": evaluacion_id,
        "rubro_id": usuario.rubro_id,
        "comparativas": comparativas,
    }