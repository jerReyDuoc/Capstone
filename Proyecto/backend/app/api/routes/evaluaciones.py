from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencias.alcance import actor_de_evaluaciones, alcance_evaluacion, solo_admin
from app.api.dependencias.consultas import consultar_evaluaciones_uc
from app.api.schemas.comunes import (
    EvaluacionResumenResponse,
    RespuestaResumenResponse,
)
from app.api.schemas.evaluaciones_esquemas import MarcarPruebaRequest
from app.application.evaluacion.casos_uso.consultar_evaluaciones import (
    ConsultarEvaluacionesUseCase,
    EvaluacionNoEncontradaError,
)
from app.domain.auth.actor import Actor


router = APIRouter(prefix="/api/evaluaciones", tags=["evaluaciones"])


@router.get("")
async def list_evaluaciones(
    page: int = Query(1, ge=1, description="Número de página (empieza en 1)"),
    size: int = Query(20, ge=1, le=100, description="Registros por página (máx 100)"),
    estado_progreso: str | None = Query(None, description="Filtrar por estado"),
    uc: ConsultarEvaluacionesUseCase = Depends(consultar_evaluaciones_uc),
    actor: Actor | None = Depends(actor_de_evaluaciones),
):
    """
    Lista evaluaciones con paginación.

    Ejemplo: GET /api/evaluaciones?page=1&size=20
    """
    pagina = await uc.listar(actor, page, size, estado_progreso)
    return {
        "items": [EvaluacionResumenResponse.model_validate(e) for e in pagina.items],
        "total": pagina.total,
        "page": page,
        "size": size,
        "pages": pagina.pages,
    }


@router.get("/{evaluacion_id}", response_model=EvaluacionResumenResponse, dependencies=[Depends(alcance_evaluacion)])
async def get_evaluacion(
    evaluacion_id: int,
    uc: ConsultarEvaluacionesUseCase = Depends(consultar_evaluaciones_uc),
):
    """Detalle de una evaluación."""
    try:
        return await uc.detalle(evaluacion_id)
    except EvaluacionNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{evaluacion_id}/respuestas", dependencies=[Depends(alcance_evaluacion)])
async def list_respuestas_evaluacion(
    evaluacion_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    estado_final: str | None = Query(None, description="Filtrar por estado_clasificacion_final"),
    fuente: str | None = Query(None, description="Filtrar por fuente: usuario | llm"),
    uc: ConsultarEvaluacionesUseCase = Depends(consultar_evaluaciones_uc),
):
    """
    Lista las respuestas de una evaluación con paginación.

    Ejemplo: GET /api/evaluaciones/1/respuestas?page=1&size=10
    """
    try:
        pagina = await uc.listar_respuestas(evaluacion_id, page, size, estado_final, fuente)
    except EvaluacionNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {
        "items": [RespuestaResumenResponse.model_validate(r) for r in pagina.items],
        "total": pagina.total,
        "page": page,
        "size": size,
        "pages": pagina.pages,
    }


@router.patch("/{evaluacion_id}/prueba")
async def marcar_prueba(
    evaluacion_id: int,
    payload: MarcarPruebaRequest,
    actor: Actor = Depends(solo_admin),
    uc: ConsultarEvaluacionesUseCase = Depends(consultar_evaluaciones_uc),
):
    """
    HU-19 criterio 4 (solo admin): marca (o desmarca) una evaluación como de prueba para
    que no entre al benchmark sectorial aunque esté completada. El cambio se refleja en
    el próximo recálculo del benchmark.
    """
    try:
        evaluacion = await uc.marcar_prueba(evaluacion_id, payload.es_prueba, actor)
    except EvaluacionNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"evaluacion_id": evaluacion.id, "origen": evaluacion.origen, "es_prueba": evaluacion.es_prueba}
