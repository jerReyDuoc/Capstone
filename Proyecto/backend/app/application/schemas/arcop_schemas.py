from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ------------------------------------------------------------ peticiones
class CrearSolicitudARCOPRequest(BaseModel):
    tipo: str
    descripcion: str


class CambiarEstadoARCOPRequest(BaseModel):
    estado: str
    comentario: str | None = None


class ResolverSolicitudARCOPRequest(BaseModel):
    resultado: str      # resuelta | rechazada
    respuesta: str      # texto comunicado al titular


class CancelarSolicitudARCOPRequest(BaseModel):
    motivo: str | None = None


class AportarInformacionARCOPRequest(BaseModel):
    informacion: str


# ------------------------------------------------------------ respuestas
class SolicitudARCOPResumenResponse(BaseModel):
    """Para listados: sin descripción ni respuesta (no expone texto libre)."""
    model_config = ConfigDict(from_attributes=True)
    id_solicitud: int
    tipo: str
    estado: str
    usuario_temporal_id: int
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    fecha_cierre: datetime | None
    fecha_limite_respuesta: datetime | None = None
    fecha_limite_informacion: datetime | None = None
    plazo_vencido: bool = False


class EventoSolicitudARCOPResponse(BaseModel):
    id_evento: int
    fecha: datetime
    tipo_evento: str
    estado_anterior: str | None
    estado_nuevo: str
    actor_rol: str
    actor_id: int | None    # solo visible para admin_therion
    comentario: str | None


class SolicitudARCOPDetalleResponse(SolicitudARCOPResumenResponse):
    descripcion: str
    respuesta: str | None
    transiciones_posibles: list[str]
    historial: list[EventoSolicitudARCOPResponse] = []
