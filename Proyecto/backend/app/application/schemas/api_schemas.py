from datetime import date
from pydantic import BaseModel, ConfigDict

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


# ============================================================
# Schemas de catálogos
# ============================================================

class DominioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre_dominio: str | None


class RubroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre_rubro: str | None


class RutaFormativaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str | None


class BrechaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_brecha: int
    codigo_brecha: str | None
    categoria: str | None
    comportamiento_detectado: str | None
    criticidad: str | None
    accion_sistema: str | None
    ruta_formativa: RutaFormativaResponse | None = None


# ============================================================
# Schemas de controles
# ============================================================

class BrechaResumenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_brecha: int
    codigo_brecha: str | None
    comportamiento_detectado: str | None
    criticidad: str | None
    accion_sistema: str | None
    ruta_formativa: RutaFormativaResponse | None = None


class ControlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_control: int
    codigo_control: str | None
    framework_fuente: str | None
    articulo_referencia: str | None
    tipo_fuente: str | None
    obligacion: str | None
    pregunta_evaluacion: str | None
    aplicabilidad: str | None
    evidencia_esperada: str | None
    criticidad: str | None
    recomendacion: str | None
    test_asociado: str | None
    dominio: DominioResponse | None = None
    brecha: BrechaResumenResponse | None = None


# ============================================================
# Schemas de evaluaciones (con paginación)
# ============================================================

class EvaluacionResumenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha_inicio: date | None
    estado_progreso: str | None
    usuario_temporal_id: int | None


class RespuestaResumenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_respuesta: int
    estado_clasificacion: str | None
    estado_clasificacion_final: str | None
    fuente_clasificacion: str | None
    confianza_clasificacion: float | None
    fecha_validacion: date | None
    matriz_controles_id_control: int | None
    catalogo_brechas_id_brecha: int | None


class PaginatedResponse(BaseModel):
    """Respuesta genérica con paginación."""
    items: list
    total: int
    page: int
    size: int
    pages: int

# ============================================================
# Schemas del filtro de aplicabilidad
# ============================================================

class PreguntaFiltroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_pregunta: int
    codigo: str
    orden: int
    pregunta: str
    descripcion: str | None


class RespuestaFiltroItem(BaseModel):
    codigo: str          # "F1", "F2", ..., "F7"
    respuesta: bool


class GuardarRespuestasFiltroRequest(BaseModel):
    respuestas: list[RespuestaFiltroItem]


class RespuestaFiltroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_respuesta_filtro: int
    pregunta_id: int
    respuesta: bool
    fecha_respuesta: date


class EstadoFiltroResponse(BaseModel):
    evaluacion_id: int
    filtro_completado: bool
    fecha_filtro: date | None
    preguntas: list[PreguntaFiltroResponse]
    respuestas: list[RespuestaFiltroResponse] = []
    controles_aplicables: int = 0