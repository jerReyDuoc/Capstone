"""Gestión por admin_therion: cambio de estado intermedio y prórroga única del plazo."""
from app.domain.auth.actor import Actor
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP as Estado,
    EventoSolicitudARCOP as Evento,
    SolicitudARCOP,
    TipoSolicitudARCOP,
)
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.comun import (
    ESTADOS_GESTION, MAX_COMENTARIO, MIN_DESCRIPCION, OperacionNoPermitidaError, RESULTADOS_RESOLUCION,
    TransicionInvalidaError, _ahora, _sumar_dias, _texto,
)


class GestionAdminMixin:
    # ------------------------------------------------------------ admin_therion
    async def cambiar_estado(self, actor: Actor, solicitud_id: int, estado: str,
                             comentario: str | None) -> SolicitudARCOP:
        if not actor.es_admin:
            raise OperacionNoPermitidaError("Solo admin_therion puede cambiar el estado.")
        if estado not in ESTADOS_GESTION:
            if estado in RESULTADOS_RESOLUCION:
                raise ValueError("Para resolver o rechazar use POST /api/arcop/solicitudes/{id}/resolucion.")
            if estado == Estado.CANCELADA.value:
                raise ValueError("La cancelación la realiza el titular (POST .../cancelacion).")
            raise ValueError(f"Estado inválido. Debe ser uno de: {', '.join(sorted(ESTADOS_GESTION))}")
        obligatorio = estado == Estado.PENDIENTE_INFORMACION.value  # qué antecedentes faltan
        comentario = _texto(comentario, "comentario", obligatorio=obligatorio)
        solicitud = await self._obtener_visible(actor, solicitud_id, para_actualizar=True)
        return await self._transicionar(actor, solicitud, estado, Evento.CAMBIO_ESTADO, comentario)

    async def prorrogar(self, actor: Actor, solicitud_id: int, motivo: str) -> SolicitudARCOP:
        """Prórroga ÚNICA del plazo de respuesta (Ley 21.719), antes de que venza."""
        if not actor.es_admin:
            raise OperacionNoPermitidaError("Solo admin_therion puede prorrogar el plazo.")
        motivo = _texto(motivo, "motivo", MIN_DESCRIPCION, MAX_COMENTARIO, obligatorio=True)
        if not self.plazo_prorroga_dias:
            raise ValueError("La prórroga no está habilitada (ARCOP_PLAZO_PRORROGA_DIAS).")
        solicitud = await self._obtener_visible(actor, solicitud_id, para_actualizar=True)
        if solicitud.tipo == TipoSolicitudARCOP.BLOQUEO.value:
            raise ValueError("El bloqueo temporal tiene plazo propio en días hábiles y no se prorroga.")
        if solicitud.estado in Estado.finales():
            raise TransicionInvalidaError(solicitud.estado, solicitud.estado,
                                          "La solicitud está cerrada: no hay plazo que prorrogar.")
        if solicitud.fecha_prorroga is not None:
            raise TransicionInvalidaError(solicitud.estado, solicitud.estado,
                                          "El plazo ya fue prorrogado una vez (la ley permite solo una).")
        if solicitud.fecha_limite_respuesta is None:
            raise ValueError("La solicitud no tiene plazo de respuesta que prorrogar.")
        ahora = _ahora()
        if solicitud.fecha_limite_respuesta < ahora:
            raise TransicionInvalidaError(solicitud.estado, solicitud.estado,
                                          "El plazo ya venció: la prórroga debe pedirse antes.")
        solicitud.fecha_limite_respuesta = _sumar_dias(solicitud.fecha_limite_respuesta, self.plazo_prorroga_dias)
        solicitud.fecha_prorroga = ahora
        solicitud.fecha_actualizacion = ahora
        evento = self._evento(actor, Evento.PRORROGA, solicitud.estado, solicitud.estado,
                              f"Plazo prorrogado {self.plazo_prorroga_dias} días. Motivo: {motivo}")
        return await self.repo.guardar(solicitud, evento)
