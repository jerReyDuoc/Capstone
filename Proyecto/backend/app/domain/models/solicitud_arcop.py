from datetime import datetime
from enum import Enum
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class TipoSolicitudARCOP(str, Enum):
    """Derechos que el titular puede ejercer (historia de usuario ARCOP)."""
    ACCESO = "acceso"
    RECTIFICACION = "rectificacion"
    SUPRESION = "supresion"
    OPOSICION = "oposicion"
    PORTABILIDAD = "portabilidad"
    BLOQUEO = "bloqueo"

    @classmethod
    def valores(cls) -> list[str]:
        return [t.value for t in cls]


class EstadoSolicitudARCOP(str, Enum):
    RECIBIDA = "recibida"
    EN_REVISION = "en_revision"
    # El responsable pidió antecedentes al titular; vuelve a en_revision cuando los aporta
    PENDIENTE_INFORMACION = "pendiente_informacion"
    EN_PROCESO = "en_proceso"
    RESUELTA = "resuelta"
    RECHAZADA = "rechazada"
    CANCELADA = "cancelada"

    @classmethod
    def valores(cls) -> list[str]:
        return [e.value for e in cls]

    @classmethod
    def finales(cls) -> set[str]:
        return {cls.RESUELTA.value, cls.RECHAZADA.value, cls.CANCELADA.value}


class EventoSolicitudARCOP(str, Enum):
    CREADA = "creada"
    CAMBIO_ESTADO = "cambio_estado"
    INFORMACION_APORTADA = "informacion_aportada"
    RESOLUCION = "resolucion"
    CANCELACION = "cancelacion"
    ANONIMIZACION = "anonimizacion"


_E = EstadoSolicitudARCOP

# Máquina de estados: estado actual -> estados a los que se puede pasar.
# La regla de QUIÉN puede hacer cada transición vive en el caso de uso.
TRANSICIONES_ARCOP: dict[str, set[str]] = {
    _E.RECIBIDA.value: {_E.EN_REVISION.value, _E.RECHAZADA.value, _E.CANCELADA.value},
    _E.EN_REVISION.value: {
        _E.EN_PROCESO.value, _E.PENDIENTE_INFORMACION.value, _E.RECHAZADA.value, _E.CANCELADA.value,
    },
    _E.PENDIENTE_INFORMACION.value: {_E.EN_REVISION.value, _E.RECHAZADA.value, _E.CANCELADA.value},
    _E.EN_PROCESO.value: {_E.RESUELTA.value, _E.RECHAZADA.value},
    _E.RESUELTA.value: set(),
    _E.RECHAZADA.value: set(),
    _E.CANCELADA.value: set(),
}


def transicion_permitida(actual: str, nuevo: str) -> bool:
    return nuevo in TRANSICIONES_ARCOP.get(actual, set())


class SolicitudARCOP(Base):
    """
    Solicitud formal de un titular de datos personales para ejercer un derecho
    ARCOP (Acceso, Rectificación, Supresión, Oposición, Portabilidad, Bloqueo).
    El titular es un usuario de la plataforma (usuario_temporal).
    """
    __tablename__ = "solicitudes_arcop"

    id: Mapped[int] = mapped_column("id_solicitud", Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column("tipo", String(20), nullable=False)
    estado: Mapped[str] = mapped_column("estado", String(25), nullable=False, index=True)
    descripcion: Mapped[str] = mapped_column("descripcion", Text, nullable=False)

    usuario_temporal_id: Mapped[int] = mapped_column(
        "Usuario_temporal_id",
        Integer,
        ForeignKey("usuario_temporal.id"),
        nullable=False,
        index=True,
    )

    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)
    # Se fija al llegar a un estado final (resuelta, rechazada o cancelada)
    fecha_cierre: Mapped[datetime | None] = mapped_column("fecha_cierre", DateTime, nullable=True)

    # Plazos (ARCOP_PLAZO_*_DIAS en config). Quedan en NULL mientras no se definan.
    fecha_limite_respuesta: Mapped[datetime | None] = mapped_column(
        "fecha_limite_respuesta", DateTime, nullable=True
    )
    # Solo mientras está en pendiente_informacion: hasta cuándo puede responder el titular
    fecha_limite_informacion: Mapped[datetime | None] = mapped_column(
        "fecha_limite_informacion", DateTime, nullable=True
    )

    # Respuesta/resolución comunicada al titular (obligatoria al resolver o rechazar)
    respuesta: Mapped[str | None] = mapped_column("respuesta", Text, nullable=True)

    eventos: Mapped[list["EventoSolicitud"]] = relationship(
        back_populates="solicitud",
        cascade="all, delete-orphan",
        order_by="EventoSolicitud.id",
    )


class EventoSolicitud(Base):
    """
    Historial (trazabilidad) de una solicitud ARCOP: quién hizo qué y cuándo.
    Lo escribe SIEMPRE el backend, en la misma transacción que el cambio.
    """
    __tablename__ = "eventos_solicitud_arcop"

    id: Mapped[int] = mapped_column("id_evento", Integer, primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(
        "Solicitudes_arcop_id_solicitud",
        Integer,
        ForeignKey("solicitudes_arcop.id_solicitud"),
        nullable=False,
        index=True,
    )
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    tipo_evento: Mapped[str] = mapped_column("tipo_evento", String(25), nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column("estado_anterior", String(25), nullable=True)
    estado_nuevo: Mapped[str] = mapped_column("estado_nuevo", String(25), nullable=False)
    # Rol e id del actor tal como los entrega la autenticación (app/core/autenticacion.py)
    actor_rol: Mapped[str] = mapped_column("actor_rol", String(20), nullable=False)
    actor_id: Mapped[int | None] = mapped_column("actor_id", Integer, nullable=True)
    comentario: Mapped[str | None] = mapped_column("comentario", Text, nullable=True)

    solicitud: Mapped["SolicitudARCOP"] = relationship(back_populates="eventos")
