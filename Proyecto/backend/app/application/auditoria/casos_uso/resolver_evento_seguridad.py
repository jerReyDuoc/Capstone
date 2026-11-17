"""HU-20/HU-22: el admin revisa o resuelve un evento de seguridad (bandeja del Oficial de Cumplimiento)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fabricas import fabricas
from app.application.seguridad.huella import huella
from app.domain.auditoria.acciones import Accion
from app.domain.auth.actor import Actor
from app.domain.models.evento_seguridad import EventoSeguridad
from app.domain.ports.repositorios_admin import EventoSeguridadRepositoryPort


class EventoNoEncontradoError(Exception):
    """El evento de seguridad no existe."""


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ResolverEventoSeguridadUseCase:
    def __init__(self, db: AsyncSession, repo: EventoSeguridadRepositoryPort):
        self.db = db
        self.repo = repo
        self.bitacora = fabricas().bitacora(db)

    async def marcar_revisado(self, evento_id: int, admin: Actor) -> EventoSeguridad:
        """Revisado sin veredicto (compatibilidad). Idempotente: solo registra la primera vez."""
        evento = await self.repo.get(evento_id)
        if not evento:
            raise EventoNoEncontradoError()
        if not evento.revisado:
            self.bitacora.registrar(
                accion=Accion.EVENTO_SEGURIDAD_REVISADO, entidad="eventos_seguridad", entidad_id=evento.id_evento,
                actor=admin, detalle={"origen": evento.origen, "tipo": evento.tipo, "resolucion": None,
                                      "evaluacion_id": evento.evaluacion_id, "respuesta_id": evento.respuesta_id})
            evento.revisado = True
            evento.fecha_revision = _ahora()
            evento.revisor_admin_id = admin.id
        return await self.repo.update(evento)

    async def resolver(self, evento_id: int, resolucion: str, comentario: str, admin: Actor,
                       anonimizar: Callable[[str], Awaitable[str]]) -> EventoSeguridad:
        """HU-22: veredicto + comentario (ya validado; `anonimizar` lo deja sin PII, fail-closed)."""
        evento = await self.repo.get(evento_id)
        if not evento:
            raise EventoNoEncontradoError()
        comentario = await anonimizar(comentario)

        self.bitacora.registrar(
            accion=Accion.EVENTO_SEGURIDAD_REVISADO, entidad="eventos_seguridad", entidad_id=evento.id_evento,
            actor=admin,
            detalle={"origen": evento.origen, "tipo": evento.tipo,
                     "resolucion": resolucion, "resolucion_anterior": evento.resolucion,
                     "evaluacion_id": evento.evaluacion_id, "respuesta_id": evento.respuesta_id,
                     "comentario_huella": huella(comentario), "comentario_largo": len(comentario)},
        )
        evento.revisado = True
        evento.resolucion = resolucion
        evento.comentario_revision = comentario
        evento.fecha_revision = _ahora()
        evento.revisor_admin_id = admin.id
        return await self.repo.update(evento)
