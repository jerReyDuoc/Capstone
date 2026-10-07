from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.application.schemas.api_schemas import ControlResponse
from app.domain.models.matriz_control import MatrizControl


router = APIRouter(prefix="/api/controles", tags=["controles"])


@router.get("", response_model=list[ControlResponse])
async def list_controles(
    dominio_id: int | None = Query(None, description="Filtrar por dominio"),
    criticidad: str | None = Query(None, description="Filtrar por criticidad: Alta, Media, Baja"),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista todos los controles. Sin paginación porque son 40 registros fijos.

    Filtros opcionales:
    - dominio_id: para obtener solo los controles de un dominio
    - criticidad: para obtener solo los de una criticidad específica
    """
    query = select(MatrizControl).order_by(MatrizControl.id_control)

    if dominio_id is not None:
        query = query.where(MatrizControl.dominio_id == dominio_id)

    if criticidad is not None:
        query = query.where(MatrizControl.criticidad == criticidad)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{control_id}", response_model=ControlResponse)
async def get_control(
    control_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detalle de un control específico, con dominio y brecha anidados."""
    result = await db.execute(
        select(MatrizControl).where(MatrizControl.id_control == control_id)
    )
    control = result.scalar_one_or_none()

    if not control:
        raise HTTPException(status_code=404, detail="Control no encontrado")

    return control