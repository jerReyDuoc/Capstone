"""Ayudas internas del caso de uso: plazos, eventos, visibilidad y transiciones de estado."""
from datetime import datetime

from app.domain.auth.actor import Actor, Rol
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP as Estado,
    EventoSolicitud,
    EventoSolicitudARCOP as Evento,
    SolicitudARCOP,
    TipoSolicitudARCOP,
    transicion_permitida,
)
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.comun import (
    SolicitudNoEncontradaError, TransicionInvalidaError, _ahora, _sumar_dias, _sumar_dias_habiles,
)


class BaseSolicitudMixin:
    """Requiere en `self`: repo y los plazos configurados (los define el constructor de casos.py)."""

    def _limite_respuesta(self, tipo: str, desde: datetime) -> datetime | None:
        if tipo == TipoSolicitudARCOP.BLOQUEO.value and self.plazo_bloqueo_dias_habiles:
            return _sumar_dias_habiles(desde, self.plazo_bloqueo_dias_habiles)
        return _sumar_dias(desde, self.plazo_respuesta_dias)

    # ------------------------------------------------------------ helpers
    def _evento(self, actor: Actor, tipo: Evento, anterior: str | None, nuevo: str,
                comentario: str | None = None) -> EventoSolicitud:
        return EventoSolicitud(
            fecha=_ahora(),
            tipo_evento=tipo.value,
            estado_anterior=anterior,
            estado_nuevo=nuevo,
            actor_rol=actor.rol,
            actor_id=actor.id,
            comentario=comentario,
        )

    @staticmethod
    def _es_dueno(actor: Actor, solicitud: SolicitudARCOP) -> bool:
        if actor.rol == Rol.REFERENTE.value:
            return solicitud.usuario_temporal_id == actor.id
        if actor.rol == Rol.ENCUESTADO.value:
            return solicitud.evaluacion_id == actor.id
        if actor.rol == Rol.CLIENTE.value:  # HU-30
            return solicitud.usuario_definitivo_id == actor.id
        return False

    async def _obtener_visible(self, actor: Actor, solicitud_id: int,
                               para_actualizar: bool = False) -> SolicitudARCOP:
        solicitud = await self.repo.get(solicitud_id, para_actualizar=para_actualizar)
        if not solicitud or (not actor.es_admin and not self._es_dueno(actor, solicitud)):
            raise SolicitudNoEncontradaError("Solicitud no encontrada")
        return solicitud

    async def _transicionar(self, actor: Actor, solicitud: SolicitudARCOP, nuevo: str,
                            tipo_evento: Evento, comentario: str | None,
                            eventos_extra: tuple = (), auditoria_extra: dict | None = None) -> SolicitudARCOP:
        anterior = solicitud.estado
        if not transicion_permitida(anterior, nuevo):
            raise TransicionInvalidaError(anterior, nuevo)
        ahora = _ahora()
        solicitud.estado = nuevo
        solicitud.fecha_actualizacion = ahora
        if nuevo in Estado.finales():
            solicitud.fecha_cierre = ahora
        # El plazo para aportar antecedentes solo existe mientras se esperan
        if nuevo == Estado.PENDIENTE_INFORMACION.value:
            solicitud.fecha_limite_informacion = _sumar_dias(ahora, self.plazo_informacion_dias)
        else:
            solicitud.fecha_limite_informacion = None
        extra = {"auditoria_extra": auditoria_extra} if auditoria_extra else {}
        return await self.repo.guardar(
            solicitud, self._evento(actor, tipo_evento, anterior, nuevo, comentario), *eventos_extra, **extra
        )
