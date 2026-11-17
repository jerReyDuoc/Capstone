from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.respuestas import anonimizar_comentario, validar_comentario
from app.api.dependencias.alcance import solo_admin
from app.domain.auth.actor import Actor
from app.application.auditoria.casos_uso.resolver_evento_seguridad import (
    EventoNoEncontradoError, ResolverEventoSeguridadUseCase,
)
from app.core.database import get_db
from app.domain.models.evento_seguridad import ResolucionEvento
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
from app.api.schemas.eventos_seguridad_esquemas import EventoSeguridadResponse, RevisionEventoRequest

# HU-20: la bandeja de eventos de seguridad es solo para administradores de Therion Labs
router = APIRouter(prefix="/api/seguridad", tags=["seguridad"], dependencies=[Depends(solo_admin)])


@router.get("/eventos", response_model=list[EventoSeguridadResponse])
async def listar_eventos(
    solo_pendientes: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Intentos de prompt injection detectados (bandeja del Oficial de Cumplimiento)."""
    return await EventoSeguridadRepository(db).list(solo_pendientes=solo_pendientes, limit=limit)


@router.patch("/eventos/{evento_id}/revisado", response_model=EventoSeguridadResponse)
async def marcar_revisado(evento_id: int, db: AsyncSession = Depends(get_db),
                          admin: Actor = Depends(solo_admin)):
    """
    Marca el evento como revisado sin veredicto (compatibilidad). HU-22: la bandeja usa
    PATCH /eventos/{id}/revision, que exige resolución y comentario. Ambas quedan en el audit_log.
    """
    try:
        return await ResolverEventoSeguridadUseCase(db, EventoSeguridadRepository(db)).marcar_revisado(evento_id, admin)
    except EventoNoEncontradoError:
        raise HTTPException(status_code=404, detail="Evento no encontrado")


@router.patch("/eventos/{evento_id}/revision", response_model=EventoSeguridadResponse)
async def revisar_evento(evento_id: int, payload: RevisionEventoRequest, db: AsyncSession = Depends(get_db),
                         admin: Actor = Depends(solo_admin)):
    """
    HU-22: el Oficial de Cumplimiento resuelve un evento de seguridad.

    - `resolucion`: `ataque_confirmado` (la detección acertó) o `falso_positivo` (el texto era
      legítimo; si bloqueó una respuesta, corrígela en la bandeja con PATCH /api/respuestas/{id}/revision).
    - `comentario`: 10 a 1000 caracteres, se guarda anonimizado.

    Se puede volver a resolver (p. ej. cambiar el veredicto); cada resolución queda en el audit_log.
    """
    if payload.resolucion not in ResolucionEvento.valores():
        raise HTTPException(status_code=422, detail={
            "codigo": "RESOLUCION_INVALIDA", "campo": "resolucion",
            "mensaje": f"La resolución debe ser una de: {', '.join(ResolucionEvento.valores())}."})
    comentario = validar_comentario(payload.comentario)
    try:
        return await ResolverEventoSeguridadUseCase(db, EventoSeguridadRepository(db)).resolver(
            evento_id, payload.resolucion, comentario, admin, anonimizar_comentario)
    except EventoNoEncontradoError:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
