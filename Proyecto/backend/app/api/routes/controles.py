from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.schemas.comunes import ControlResponse
from app.infrastructure.repositories.catalogo_repository import CatalogoRepository


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
    return await CatalogoRepository(db).list_controles(dominio_id=dominio_id, criticidad=criticidad)


@router.get("/{control_id}", response_model=ControlResponse)
async def get_control(
    control_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Detalle de un control específico, con dominio y brecha anidados."""
    control = await CatalogoRepository(db).get_control(control_id)

    if not control:
        raise HTTPException(status_code=404, detail="Control no encontrado")

    return control
