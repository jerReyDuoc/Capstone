from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.respuestas import anonimizar_comentario, validar_comentario
from app.core.alcance import solo_admin
from app.core.autenticacion import Actor
from app.core.cliente import huella
from app.core.database import get_db
from app.domain.models.evento_seguridad import ResolucionEvento
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository

# HU-20: la bandeja de eventos de seguridad es solo para administradores de Therion Labs
router = APIRouter(prefix="/api/seguridad", tags=["seguridad"], dependencies=[Depends(solo_admin)])


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
    # HU-22
    resolucion: str | None = None
    comentario_revision: str | None = None
    fecha_revision: datetime | None = None


class RevisionEventoRequest(BaseModel):
    resolucion: str
    comentario: str | None = None


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    repo = EventoSeguridadRepository(db)
    evento = await repo.get(evento_id)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    if not evento.revisado:
        BitacoraRepository(db).registrar(
            accion=Accion.EVENTO_SEGURIDAD_REVISADO, entidad="eventos_seguridad", entidad_id=evento.id_evento,
            actor=admin, detalle={"origen": evento.origen, "tipo": evento.tipo, "resolucion": None,
                                  "evaluacion_id": evento.evaluacion_id, "respuesta_id": evento.respuesta_id})
        evento.revisado = True
        evento.fecha_revision = _ahora()
        evento.revisor_admin_id = admin.id
    return await repo.update(evento)


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
    repo = EventoSeguridadRepository(db)
    evento = await repo.get(evento_id)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    comentario = await anonimizar_comentario(comentario)

    BitacoraRepository(db).registrar(
        accion=Accion.EVENTO_SEGURIDAD_REVISADO, entidad="eventos_seguridad", entidad_id=evento.id_evento,
        actor=admin,
        detalle={"origen": evento.origen, "tipo": evento.tipo,
                 "resolucion": payload.resolucion, "resolucion_anterior": evento.resolucion,
                 "evaluacion_id": evento.evaluacion_id, "respuesta_id": evento.respuesta_id,
                 "comentario_huella": huella(comentario), "comentario_largo": len(comentario)},
    )
    evento.revisado = True
    evento.resolucion = payload.resolucion
    evento.comentario_revision = comentario
    evento.fecha_revision = _ahora()
    evento.revisor_admin_id = admin.id
    return await repo.update(evento)
