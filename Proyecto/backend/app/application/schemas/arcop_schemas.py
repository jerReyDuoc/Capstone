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


class ProrrogarSolicitudARCOPRequest(BaseModel):
    motivo: str          # se registra en el historial y justifica la prórroga


# ------------------------------------------------------------ respuestas
class SolicitudARCOPResumenResponse(BaseModel):
    """Para listados: sin descripción ni respuesta (no expone texto libre)."""
    model_config = ConfigDict(from_attributes=True)
    id_solicitud: int
    codigo_seguimiento: str
    tipo: str
    estado: str
    usuario_temporal_id: int | None      # titular invitado
    evaluacion_id: int | None = None     # titular encuestado anónimo
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    fecha_cierre: datetime | None
    fecha_limite_respuesta: datetime | None = None
    fecha_limite_informacion: datetime | None = None
    plazo_vencido: bool = False
    fecha_prorroga: datetime | None = None


class SeguimientoARCOPResponse(BaseModel):
    """Consulta pública por código: sin ids, sin textos ni datos del titular."""
    codigo_seguimiento: str
    tipo: str
    estado: str
    fecha_creacion: datetime
    fecha_actualizacion: datetime
    fecha_limite_respuesta: datetime | None
    fecha_cierre: datetime | None
    prorrogada: bool
    plazo_vencido: bool


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
