from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.application.schemas.api_schemas import (
    EvaluacionResumenResponse,
    RespuestaResumenResponse,
)
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.respuesta import Respuesta


router = APIRouter(prefix="/api/evaluaciones", tags=["evaluaciones"])


@router.get("")
async def list_evaluaciones(
    page: int = Query(1, ge=1, description="Número de página (empieza en 1)"),
    size: int = Query(20, ge=1, le=100, description="Registros por página (máx 100)"),
    estado_progreso: str | None = Query(None, description="Filtrar por estado"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista evaluaciones con paginación.

    Ejemplo: GET /api/evaluaciones?page=1&size=20
    """
    query = select(Evaluacion).order_by(Evaluacion.id.desc())
    count_query = select(func.count()).select_from(Evaluacion)

    if estado_progreso:
        query = query.where(Evaluacion.estado_progreso == estado_progreso)
        count_query = count_query.where(Evaluacion.estado_progreso == estado_progreso)

    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    result = await db.execute(query.offset(offset).limit(size))
    items = list(result.scalars().all())

    return {
        "items": [EvaluacionResumenResponse.model_validate(e) for e in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if size > 0 else 0,
    }


@router.get("/{evaluacion_id}", response_model=EvaluacionResumenResponse)
async def get_evaluacion(
    evaluacion_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detalle de una evaluación."""
    result = await db.execute(
        select(Evaluacion).where(Evaluacion.id == evaluacion_id)
    )
    evaluacion = result.scalar_one_or_none()

    if not evaluacion:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    return evaluacion


@router.get("/{evaluacion_id}/respuestas")
async def list_respuestas_evaluacion(
    evaluacion_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    estado_final: str | None = Query(None, description="Filtrar por estado_clasificacion_final"),
    fuente: str | None = Query(None, description="Filtrar por fuente: usuario | llm"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista las respuestas de una evaluación con paginación.

    Ejemplo: GET /api/evaluaciones/1/respuestas?page=1&size=10
    """
    # Verificar que la evaluación existe
    eval_exists = await db.execute(
        select(func.count()).select_from(Evaluacion).where(Evaluacion.id == evaluacion_id)
    )
    if (eval_exists.scalar() or 0) == 0:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    query = (
        select(Respuesta)
        .where(Respuesta.evaluacion_id == evaluacion_id)
        .order_by(Respuesta.id.desc())
    )
    count_query = (
        select(func.count())
        .select_from(Respuesta)
        .where(Respuesta.evaluacion_id == evaluacion_id)
    )

    if estado_final:
        query = query.where(Respuesta.estado_clasificacion_final == estado_final)
        count_query = count_query.where(Respuesta.estado_clasificacion_final == estado_final)

    if fuente:
        query = query.where(Respuesta.fuente_clasificacion == fuente)
        count_query = count_query.where(Respuesta.fuente_clasificacion == fuente)

    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * size
    result = await db.execute(query.offset(offset).limit(size))
    items = list(result.scalars().all())

    return {
        "items": [RespuestaResumenResponse.model_validate(r) for r in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if size > 0 else 0,
    }