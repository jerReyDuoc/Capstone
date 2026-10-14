"""
Ciclo de vida de las solicitudes de derechos ARCOP.

Reglas de negocio (el backend decide, nunca el cliente):
  - Solo el titular (rol referente) crea, cancela y aporta información a SUS solicitudes.
  - Solo admin_therion cambia estados intermedios y registra la resolución.
  - Un titular nunca ve solicitudes ajenas: se responde "no encontrada" (no se
    revela que el id existe).
  - Toda transición se valida contra TRANSICIONES_ARCOP y deja un evento en el
    historial en la misma transacción.
"""
from datetime import datetime, timezone

from app.core.autenticacion import Actor
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP as Estado,
    EventoSolicitud,
    EventoSolicitudARCOP as Evento,
    SolicitudARCOP,
    TipoSolicitudARCOP,
    transicion_permitida,
)

MIN_DESCRIPCION, MAX_DESCRIPCION = 10, 5000
MAX_COMENTARIO = 2000
MIN_RESPUESTA, MAX_RESPUESTA = 10, 10000

# Estados que admin_therion fija con PATCH /estado. Los finales tienen su propio
# endpoint (resolución / cancelación) porque exigen datos adicionales.
ESTADOS_GESTION = {
    Estado.EN_REVISION.value,
    Estado.PENDIENTE_INFORMACION.value,
    Estado.EN_PROCESO.value,
}
RESULTADOS_RESOLUCION = {Estado.RESUELTA.value, Estado.RECHAZADA.value}


class SolicitudNoEncontradaError(Exception):
    pass


class OperacionNoPermitidaError(Exception):
    pass


class TransicionInvalidaError(Exception):
    def __init__(self, actual: str, nuevo: str, mensaje: str | None = None):
        self.actual, self.nuevo = actual, nuevo
        super().__init__(mensaje or f"No se puede pasar de '{actual}' a '{nuevo}'.")


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _texto(valor: str | None, campo: str, minimo: int = 0, maximo: int = MAX_COMENTARIO,
           obligatorio: bool = False) -> str | None:
    texto = (valor or "").strip()
    if not texto:
        if obligatorio:
            raise ValueError(f"El campo '{campo}' es obligatorio.")
        return None
    if len(texto) < minimo:
        raise ValueError(f"El campo '{campo}' debe tener al menos {minimo} caracteres.")
    if len(texto) > maximo:
        raise ValueError(f"El campo '{campo}' no puede superar {maximo} caracteres.")
    return texto


class GestionarSolicitudARCOPUseCase:
    def __init__(self, repo):
        self.repo = repo

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

    async def _obtener_visible(self, actor: Actor, solicitud_id: int,
                               para_actualizar: bool = False) -> SolicitudARCOP:
        solicitud = await self.repo.get(solicitud_id, para_actualizar=para_actualizar)
        if not solicitud or (not actor.es_admin and solicitud.usuario_temporal_id != actor.id):
            raise SolicitudNoEncontradaError("Solicitud no encontrada")
        return solicitud

    async def _transicionar(self, actor: Actor, solicitud: SolicitudARCOP, nuevo: str,
                            tipo_evento: Evento, comentario: str | None) -> SolicitudARCOP:
        anterior = solicitud.estado
        if not transicion_permitida(anterior, nuevo):
            raise TransicionInvalidaError(anterior, nuevo)
        ahora = _ahora()
        solicitud.estado = nuevo
        solicitud.fecha_actualizacion = ahora
        if nuevo in Estado.finales():
            solicitud.fecha_cierre = ahora
        return await self.repo.guardar(
            solicitud, self._evento(actor, tipo_evento, anterior, nuevo, comentario)
        )

    # ------------------------------------------------------------ titular
    async def crear(self, actor: Actor, tipo: str, descripcion: str) -> SolicitudARCOP:
        if actor.es_admin:
            raise OperacionNoPermitidaError("Las solicitudes ARCOP las registra el titular.")
        if tipo not in TipoSolicitudARCOP.valores():
            raise ValueError(
                f"Tipo de solicitud inválido. Debe ser uno de: {', '.join(TipoSolicitudARCOP.valores())}"
            )
        texto = _texto(descripcion, "descripcion", MIN_DESCRIPCION, MAX_DESCRIPCION, obligatorio=True)
        if not await self.repo.existe_usuario(actor.id):
            raise OperacionNoPermitidaError("El usuario del token no existe.")

        ahora = _ahora()
        solicitud = SolicitudARCOP(
            tipo=tipo,
            estado=Estado.RECIBIDA.value,
            descripcion=texto,
            usuario_temporal_id=actor.id,
            fecha_creacion=ahora,
            fecha_actualizacion=ahora,
        )
        evento = self._evento(actor, Evento.CREADA, None, Estado.RECIBIDA.value)
        return await self.repo.create(solicitud, evento)

    async def cancelar(self, actor: Actor, solicitud_id: int, motivo: str | None) -> SolicitudARCOP:
        if actor.es_admin:
            raise OperacionNoPermitidaError("Solo el titular puede cancelar su solicitud.")
        motivo = _texto(motivo, "motivo")
        solicitud = await self._obtener_visible(actor, solicitud_id, para_actualizar=True)
        return await self._transicionar(actor, solicitud, Estado.CANCELADA.value, Evento.CANCELACION, motivo)

    async def aportar_informacion(self, actor: Actor, solicitud_id: int, informacion: str) -> SolicitudARCOP:
        if actor.es_admin:
            raise OperacionNoPermitidaError("Solo el titular puede aportar información a su solicitud.")
        texto = _texto(informacion, "informacion", MIN_DESCRIPCION, MAX_DESCRIPCION, obligatorio=True)
        solicitud = await self._obtener_visible(actor, solicitud_id, para_actualizar=True)
        if solicitud.estado != Estado.PENDIENTE_INFORMACION.value:
            raise TransicionInvalidaError(
                solicitud.estado, Estado.EN_REVISION.value,
                "Solo se puede aportar información cuando la solicitud está en 'pendiente_informacion'.",
            )
        return await self._transicionar(
            actor, solicitud, Estado.EN_REVISION.value, Evento.INFORMACION_APORTADA, texto
        )

    # ------------------------------------------------------------ consulta
    async def obtener(self, actor: Actor, solicitud_id: int) -> SolicitudARCOP:
        return await self._obtener_visible(actor, solicitud_id)

    async def listar(self, actor: Actor, estado: str | None, tipo: str | None,
                     usuario_temporal_id: int | None, page: int, size: int):
        if estado and estado not in Estado.valores():
            raise ValueError(f"Estado inválido. Debe ser uno de: {', '.join(Estado.valores())}")
        if tipo and tipo not in TipoSolicitudARCOP.valores():
            raise ValueError(f"Tipo inválido. Debe ser uno de: {', '.join(TipoSolicitudARCOP.valores())}")
        # El titular SIEMPRE queda filtrado a sus propias solicitudes
        dueno = usuario_temporal_id if actor.es_admin else actor.id
        return await self.repo.list(
            usuario_temporal_id=dueno, estado=estado, tipo=tipo,
            offset=(page - 1) * size, limit=size,
        )

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

    async def resolver(self, actor: Actor, solicitud_id: int, resultado: str,
                       respuesta: str) -> SolicitudARCOP:
        if not actor.es_admin:
            raise OperacionNoPermitidaError("Solo admin_therion puede resolver solicitudes.")
        if resultado not in RESULTADOS_RESOLUCION:
            raise ValueError(f"Resultado inválido. Debe ser uno de: {', '.join(sorted(RESULTADOS_RESOLUCION))}")
        texto = _texto(respuesta, "respuesta", MIN_RESPUESTA, MAX_RESPUESTA, obligatorio=True)
        solicitud = await self._obtener_visible(actor, solicitud_id, para_actualizar=True)
        if not transicion_permitida(solicitud.estado, resultado):
            raise TransicionInvalidaError(solicitud.estado, resultado)
        solicitud.respuesta = texto
        return await self._transicionar(actor, solicitud, resultado, Evento.RESOLUCION, None)
