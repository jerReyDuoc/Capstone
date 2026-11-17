"""Acciones del titular sobre su solicitud: crear, cancelar y aportar información."""
from app.domain.auth.actor import Actor
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP as Estado,
    EventoSolicitudARCOP as Evento,
    SolicitudARCOP,
    TipoSolicitudARCOP,
)
from app.application.arcop.casos_uso.gestionar_solicitud_arcop.comun import (
    MAX_DESCRIPCION, MIN_DESCRIPCION, OperacionNoPermitidaError, TransicionInvalidaError, _ahora, _texto,
    nuevo_codigo_seguimiento,
)


class AccionesTitularMixin:
    # ------------------------------------------------------------ titular
    async def crear(self, actor: Actor, tipo: str, descripcion: str) -> SolicitudARCOP:
        if actor.es_admin:
            raise OperacionNoPermitidaError("Las solicitudes ARCOP las registra el titular.")
        if tipo not in TipoSolicitudARCOP.valores():
            raise ValueError(
                f"Tipo de solicitud inválido. Debe ser uno de: {', '.join(TipoSolicitudARCOP.valores())}"
            )
        texto = _texto(descripcion, "descripcion", MIN_DESCRIPCION, MAX_DESCRIPCION, obligatorio=True)
        if actor.es_encuestado:
            if not await self.repo.existe_evaluacion(actor.id):
                raise OperacionNoPermitidaError("La evaluación del token no existe.")
            dueno = {"evaluacion_id": actor.id}
        elif actor.es_cliente:
            # HU-30: el usuario de la empresa cliente ejerce sus derechos con o sin contrato vigente
            if not await self.repo.existe_usuario_definitivo(actor.id):
                raise OperacionNoPermitidaError("El usuario del token no existe.")
            dueno = {"usuario_definitivo_id": actor.id}
        else:
            if not await self.repo.existe_usuario(actor.id):
                raise OperacionNoPermitidaError("El usuario del token no existe.")
            dueno = {"usuario_temporal_id": actor.id}

        ahora = _ahora()
        solicitud = SolicitudARCOP(
            codigo_seguimiento=await self._codigo_libre(),
            tipo=tipo,
            estado=Estado.RECIBIDA.value,
            descripcion=texto,
            fecha_creacion=ahora,
            fecha_actualizacion=ahora,
            fecha_limite_respuesta=self._limite_respuesta(tipo, ahora),
            **dueno,
        )
        evento = self._evento(actor, Evento.CREADA, None, Estado.RECIBIDA.value)
        return await self.repo.create(solicitud, evento)

    async def _codigo_libre(self) -> str:
        # 40 bits de azar: un choque es casi imposible, pero se verifica igual.
        for _ in range(5):
            codigo = nuevo_codigo_seguimiento()
            if not await self.repo.existe_codigo(codigo):
                return codigo
        raise RuntimeError("No se pudo generar un código de seguimiento único.")

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
