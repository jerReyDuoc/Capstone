from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.application.schemas.api_schemas import (
    DominioResponse,
    RubroResponse,
    RutaFormativaResponse,
    BrechaResponse,
)
from app.infrastructure.repositories.catalogo_repository import CatalogoRepository


router = APIRouter(prefix="/api", tags=["catalogos"])


@router.get("/dominios", response_model=list[DominioResponse])
async def list_dominios(db: AsyncSession = Depends(get_db)):
    repo = CatalogoRepository(db)
    return await repo.list_dominios()


@router.get("/rubros", response_model=list[RubroResponse])
async def list_rubros(db: AsyncSession = Depends(get_db)):
    repo = CatalogoRepository(db)
    return await repo.list_rubros()


@router.get("/rutas-formativas", response_model=list[RutaFormativaResponse])
async def list_rutas_formativas(db: AsyncSession = Depends(get_db)):
    repo = CatalogoRepository(db)
    return await repo.list_rutas_formativas()


@router.get("/brechas", response_model=list[BrechaResponse])
async def list_brechas(db: AsyncSession = Depends(get_db)):
    repo = CatalogoRepository(db)
    return await repo.list_brechas()