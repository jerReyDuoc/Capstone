from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.schemas.api_schemas import ControlResponse, ProgresoCuestionarioResponse
from app.application.use_cases.progreso_cuestionario import calcular_progreso
from app.infrastructure.cache import catalogo_controles
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository

from app.core.alcance import alcance_evaluacion
from app.core.database import get_db
from app.application.use_cases.responder_filtro import ResponderFiltroUseCase
from app.application.schemas.api_schemas import (
    PreguntaFiltroResponse,
    EstadoFiltroResponse,
    RespuestaFiltroResponse,
    GuardarRespuestasFiltroRequest,
)
from app.application.filters.control_tree import get_controles_aplicables
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.pregunta_filtro_repository import PreguntaFiltroRepository
from app.infrastructure.repositories.respuesta_filtro_repository import RespuestaFiltroRepository


# HU-19: todas las rutas llevan {evaluacion_id}; el encuestado solo accede a la suya.
router = APIRouter(prefix="/api/evaluaciones", tags=["filtro"], dependencies=[Depends(alcance_evaluacion)])


@router.get("/{evaluacion_id}/filtro", response_model=EstadoFiltroResponse)
async def get_estado_filtro(evaluacion_id: int, db: AsyncSession = Depends(get_db)):
    """
    Devuelve las 7 preguntas de compuerta y, si ya fueron respondidas,
    las respuestas guardadas.
    """
    eval_repo = EvaluacionRepository(db)
    preg_repo = PreguntaFiltroRepository(db)
    resp_repo = RespuestaFiltroRepository(db)

    evaluacion = await eval_repo.get(evaluacion_id)
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    preguntas = await preg_repo.list_activas()
    respuestas = await resp_repo.list_by_evaluacion(evaluacion_id)

    controles_count = 0
    if respuestas:
        respuestas_dict = {
            r.pregunta.codigo: r.respuesta
            for r in respuestas
            if r.pregunta is not None
        }
        controles_count = len(get_controles_aplicables(respuestas_dict))

    return EstadoFiltroResponse(
        evaluacion_id=evaluacion_id,
        filtro_completado=evaluacion.filtro_completado,
        fecha_filtro=evaluacion.fecha_filtro,
        preguntas=[PreguntaFiltroResponse.model_validate(p) for p in preguntas],
        respuestas=[RespuestaFiltroResponse.model_validate(r) for r in respuestas],
        controles_aplicables=controles_count,
    )


@router.post("/{evaluacion_id}/filtro")
async def responder_filtro(
    evaluacion_id: int,
    payload: GuardarRespuestasFiltroRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Guarda las respuestas a las 7 preguntas y calcula qué controles aplican.

    Body esperado:
    {
      "respuestas": [
        {"codigo": "F1", "respuesta": true},
        {"codigo": "F2", "respuesta": false},
        ...
      ]
    }
    """
    use_case = ResponderFiltroUseCase(
        evaluacion_repo=EvaluacionRepository(db),
        pregunta_repo=PreguntaFiltroRepository(db),
        respuesta_repo=RespuestaFiltroRepository(db),
    )

    respuestas_dict = {item.codigo: item.respuesta for item in payload.respuestas}

    try:
        return await use_case.execute(evaluacion_id, respuestas_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{evaluacion_id}/controles-aplicables", response_model=list[ControlResponse])
async def listar_controles_aplicables(
    evaluacion_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve solo los controles que aplican a esta evaluación,
    según las respuestas del filtro.

    HU-01 C4: una sola consulta (evaluación + filtro) y el catálogo de controles
    sale de una caché en memoria ya serializada (ver catalogo_controles.py).
    """
    contexto = await EvaluacionRepository(db).get_contexto(evaluacion_id)
    if contexto is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    if not contexto.filtro_completado:
        raise HTTPException(
            status_code=400,
            detail="La evaluación aún no ha completado el filtro de aplicabilidad"
        )

    cuerpo = await catalogo_controles.json_controles(db, contexto.codigos_aplicables)
    return Response(content=cuerpo, media_type="application/json")


@router.get("/{evaluacion_id}/progreso", response_model=ProgresoCuestionarioResponse)
async def progreso_cuestionario(
    evaluacion_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Progreso del cuestionario para **reanudarlo** (HU-01): controles respondidos /
    aplicables, desglose por dimensión, el siguiente control pendiente y el estado
    declarado de cada control ya respondido.

    `etapa` indica dónde retomar: `filtro` (falta F1–F7), `cuestionario`
    (quedan controles pendientes), `completo` (todos respondidos) o `cerrada`.
    """
    contexto = await EvaluacionRepository(db).get_contexto(evaluacion_id)
    if contexto is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    catalogo = await catalogo_controles.obtener(db)
    filas = await RespuestaRepository(db).list_estado_por_evaluacion(evaluacion_id)
    return calcular_progreso(contexto, catalogo, filas)
