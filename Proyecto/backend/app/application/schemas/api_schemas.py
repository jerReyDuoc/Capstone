from datetime import date
from pydantic import BaseModel

class EvidenciaUploadResponse(BaseModel):
    id_evidencia: int
    nombre_archivo: str
    estado_validacion: str
    mensaje: str

class EvidenciaDetalleResponse(BaseModel):
    id_evidencia: int
    nombre_archivo: str
    estado_validacion: str
    clasificacion_llm: str | None
    confianza: float | None
    justificacion_llm: str | None
    datos_extraidos: dict | None
    errores_validacion: list | None
    fecha_subida: date | None
    fecha_procesada: date | None

class RespuestaDetalleResponse(BaseModel):
    id_respuesta: int
    estado_clasificacion: str | None
    justificacion_usuario: str | None
    estado_clasificacion_final: str | None
    fuente_clasificacion: str | None
    confianza_clasificacion: float | None
    fecha_validacion: date | None
    evidencias: list[EvidenciaDetalleResponse] = []