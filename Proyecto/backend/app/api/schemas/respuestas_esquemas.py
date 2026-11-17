from pydantic import BaseModel


class CrearRespuestaRequest(BaseModel):
    evaluacion_id: int
    matriz_control_id: int
    estado_clasificacion: str
    justificacion: str


class ActualizarRespuestaRequest(BaseModel):
    estado_clasificacion: str
    justificacion: str


class RevisionRequest(BaseModel):
    clasificacion_revisada: str
    # HU-22 criterio 2: confirmar o corregir SIEMPRE lleva un comentario del oficial
    comentario: str | None = None
