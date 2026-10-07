from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository

router = APIRouter(prefix="/api/seguridad", tags=["seguridad"])


class EventoSeguridadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_evento: int
    fecha: datetime
    tipo: str
    origen: str
    evaluacion_id: int | None
    matriz_control_id: int | None
    respuesta_id: int | None
    evidencia_id: int | None
    extracto: str | None
    revisado: bool


@router.get("/eventos", response_model=list[EventoSeguridadResponse])
async def listar_eventos(
    solo_pendientes: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Intentos de prompt injection detectados (bandeja del Oficial de Cumplimiento)."""
    return await EventoSeguridadRepository(db).list(solo_pendientes=solo_pendientes, limit=limit)


@router.patch("/eventos/{evento_id}/revisado", response_model=EventoSeguridadResponse)
async def marcar_revisado(evento_id: int, db: AsyncSession = Depends(get_db)):
    repo = EventoSeguridadRepository(db)
    evento = await repo.get(evento_id)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    evento.revisado = True
    return await repo.update(evento)
