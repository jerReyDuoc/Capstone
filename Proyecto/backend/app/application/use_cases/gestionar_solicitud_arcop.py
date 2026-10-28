"""
Ciclo de vida de las solicitudes de derechos ARCOP.

Reglas de negocio (el backend decide, nunca el cliente):
  - Titular = invitado (rol referente) o encuestado anónimo de la encuesta pública
    (rol encuestado). Solo el titular crea, cancela y aporta información a SUS solicitudes.
  - Solo admin_therion cambia estados intermedios y registra la resolución.
  - Un titular nunca ve solicitudes ajenas: se responde "no encontrada" (no se
    revela que el id existe).
  - Toda transición se valida contra TRANSICIONES_ARCOP y deja un evento en el
    historial en la misma transacción.
  - Una SUPRESIÓN aprobada (resuelta) anonimiza los datos del titular en la misma
    transacción que la resolución (ver AnonimizacionRepository).
  - Cada solicitud tiene un código de seguimiento único (ARC-XXXX-XXXX).
  - Plazos (Ley 21.719): respuesta en 30 días corridos, prorrogable UNA vez por 30 días
    más con motivo; el bloqueo temporal se responde en 2 días hábiles (configurables).
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from app.core.autenticacion import Actor, Rol
from app.domain.models.solicitud_arcop import (
    EstadoSolicitudARCOP as Estado,
    EventoSolicitud,
    EventoSolicitudARCOP as Evento,
    SolicitudARCOP,
    TipoSolicitudARCOP,
    transicion_permitida,
)

logger = logging.getLogger("arcop")

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


def plazo_vencido(solicitud: SolicitudARCOP, ahora: datetime | None = None) -> bool:
    """True si la solicitud sigue abierta y pasó alguno de sus plazos."""
    if solicitud.estado in Estado.finales():
        return False
    ahora = ahora or _ahora()
    if solicitud.fecha_limite_respuesta and solicitud.fecha_limite_respuesta < ahora:
        return True
    return bool(
        solicitud.estado == Estado.PENDIENTE_INFORMACION.value
        and solicitud.fecha_limite_informacion
        and solicitud.fecha_limite_informacion < ahora
    )


def _sumar_dias(desde: datetime, dias: int | None) -> datetime | None:
    """Días CORRIDOS. None o 0 = sin plazo."""
    return desde + timedelta(days=dias) if dias else None


def _sumar_dias_habiles(desde: datetime, dias: int | None) -> datetime | None:
    """
    Días HÁBILES: de lunes a viernes. NO descuenta feriados (no hay calendario de
    feriados en el proyecto): si uno cae dentro del plazo, el límite real es un día después.
    """
    if not dias:
        return None
    fecha, restantes = desde, dias
    while restantes > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:  # 0=lunes ... 4=viernes
            restantes -= 1
    return fecha


_ALFABETO_CODIGO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32 (sin I, L, O, U)
_TRADUCCION_CODIGO = str.maketrans({"O": "0", "I": "1", "L": "1"})


def nuevo_codigo_seguimiento() -> str:
    """ARC-XXXX-XXXX: 8 caracteres al azar (40 bits). No revela el id ni el orden."""
    c = "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(8))
    return f"ARC-{c[:4]}-{c[4:]}"


def normalizar_codigo(codigo: str) -> str:
    """Acepta minúsculas, espacios, sin guiones y confusiones O/0, I/L/1."""
    limpio = "".join(ch for ch in (codigo or "").upper() if ch.isalnum()).translate(_TRADUCCION_CODIGO)
    if limpio.startswith("ARC"):
        limpio = limpio[3:]
    if len(limpio) != 8:
        return ""
    return f"ARC-{limpio[:4]}-{limpio[4:]}"


class GestionarSolicitudARCOPUseCase:
    def __init__(self, repo, anonimizacion_repo=None, storage=None,
                 plazo_respuesta_dias: int | None = None,
                 plazo_informacion_dias: int | None = None,
                 plazo_prorroga_dias: int | None = None,
                 plazo_bloqueo_dias_habiles: int | None = None):
        self.repo = repo
        self.anonimizacion_repo = anonimizacion_repo
        self.storage = storage
        self.plazo_respuesta_dias = plazo_respuesta_dias
        self.plazo_informacion_dias = plazo_informacion_dias
        self.plazo_prorroga_dias = plazo_prorroga_dias
        self.plazo_bloqueo_dias_habiles = plazo_bloqueo_dias_habiles

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
                            eventos_extra: tuple = ()) -> SolicitudARCOP:
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
        return await self.repo.guardar(
            solicitud, self._evento(actor, tipo_evento, anterior, nuevo, comentario), *eventos_extra
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

    # ------------------------------------------------------------ consulta
    async def obtener(self, actor: Actor, solicitud_id: int) -> SolicitudARCOP:
        return await self._obtener_visible(actor, solicitud_id)

    async def seguimiento(self, codigo: str) -> SolicitudARCOP:
        """Consulta pública por código: el router solo expone datos sin PII."""
        normalizado = normalizar_codigo(codigo)
        solicitud = await self.repo.get_por_codigo(normalizado) if normalizado else None
        if not solicitud:
            raise SolicitudNoEncontradaError("Solicitud no encontrada")
        return solicitud

    async def listar(self, actor: Actor, estado: str | None, tipo: str | None,
                     usuario_temporal_id: int | None, page: int, size: int,
                     solo_vencidas: bool = False, evaluacion_id: int | None = None):
        if estado and estado not in Estado.valores():
            raise ValueError(f"Estado inválido. Debe ser uno de: {', '.join(Estado.valores())}")
        if tipo and tipo not in TipoSolicitudARCOP.valores():
            raise ValueError(f"Tipo inválido. Debe ser uno de: {', '.join(TipoSolicitudARCOP.valores())}")
        # El titular SIEMPRE queda filtrado a sus propias solicitudes
        if actor.es_admin:
            filtro = {"usuario_temporal_id": usuario_temporal_id, "evaluacion_id": evaluacion_id}
        elif actor.es_encuestado:
            filtro = {"usuario_temporal_id": None, "evaluacion_id": actor.id}
        elif actor.es_cliente:
            filtro = {"usuario_temporal_id": None, "evaluacion_id": None, "usuario_definitivo_id": actor.id}
        else:
            filtro = {"usuario_temporal_id": actor.id, "evaluacion_id": None}
        return await self.repo.list(
            **filtro, estado=estado, tipo=tipo,
            solo_vencidas_al=_ahora() if solo_vencidas else None,
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

        eventos_extra, rutas = (), []
        if resultado == Estado.RESUELTA.value and solicitud.tipo == TipoSolicitudARCOP.SUPRESION.value:
            if self.anonimizacion_repo is None:
                raise RuntimeError("Falta el repositorio de anonimización para resolver una supresión.")
            # Mismo commit que la resolución: si algo falla, no queda nada a medias
            if solicitud.usuario_temporal_id is not None:
                conteo, rutas = await self.anonimizacion_repo.anonimizar_titular(
                    solicitud.usuario_temporal_id, _ahora()
                )
            elif solicitud.usuario_definitivo_id is not None:  # HU-30
                conteo, rutas = await self.anonimizacion_repo.anonimizar_usuario_definitivo(
                    solicitud.usuario_definitivo_id, _ahora()
                )
            else:
                conteo, rutas = await self.anonimizacion_repo.anonimizar_encuestado(
                    solicitud.evaluacion_id, _ahora()
                )
            resumen = ", ".join(f"{k}={v}" for k, v in conteo.items())
            eventos_extra = (self._evento(
                actor, Evento.ANONIMIZACION, resultado, resultado,
                f"Datos del titular anonimizados ({resumen}).",
            ),)

        resuelta = await self._transicionar(
            actor, solicitud, resultado, Evento.RESOLUCION, None, eventos_extra
        )
        await self._borrar_archivos(solicitud_id, rutas)
        return resuelta

    async def _borrar_archivos(self, solicitud_id: int, rutas: list[str]) -> None:
        """Tras el commit: si un archivo no se puede borrar se registra para revisarlo a mano."""
        if not rutas:
            return
        fallidos = 0
        for ruta in rutas:
            try:
                await self.storage.delete(ruta)
            except Exception:  # noqa: BLE001
                fallidos += 1
        if fallidos:
            logger.error(
                "Supresión ARCOP %s: no se pudieron borrar %s de %s archivos de evidencia",
                solicitud_id, fallidos, len(rutas),
            )
