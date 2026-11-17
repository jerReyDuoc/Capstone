from datetime import datetime
from pydantic import BaseModel, ConfigDict


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
