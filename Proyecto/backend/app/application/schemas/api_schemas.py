from datetime import date
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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
    # HU-12: catálogo formativo (opcionales: las rutas antiguas solo tienen nombre)
    dominio_id: int | None = None
    nivel: str | None = None
    objetivo: str | None = None
    horas: int | None = None
    modalidad: str | None = None
    publico_objetivo: str | None = None


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
    # El modelo Respuesta expone el atributo `id` (columna id_respuesta)
    id_respuesta: int = Field(validation_alias=AliasChoices("id_respuesta", "id"))
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

# ============================================================
# Schemas del progreso del cuestionario (HU-01)
# ============================================================

class ControlPendienteResponse(BaseModel):
    id_control: int
    codigo_control: str
    dominio_id: int | None
    dominio: str | None


class ControlRespondidoResponse(ControlPendienteResponse):
    id_respuesta: int
    estado_clasificacion: str | None
    estado_clasificacion_final: str | None


class ProgresoDimensionResponse(BaseModel):
    dominio_id: int | None
    dominio: str | None
    aplicables: int
    respondidos: int
    porcentaje: float


class ProgresoCuestionarioResponse(BaseModel):
    evaluacion_id: int
    estado_progreso: str | None
    cerrada: bool
    filtro_completado: bool
    etapa: str                       # filtro | cuestionario | completo | cerrada
    controles_aplicables: int
    controles_respondidos: int
    controles_pendientes: int
    porcentaje: float                # respondidos / aplicables * 100
    # Respuestas a controles que el filtro actual ya no deja aplicables (p.ej. tras
    # rehacer el filtro). No cuentan en el progreso ni en el puntaje.
    respuestas_fuera_de_alcance: int
    por_dimension: list[ProgresoDimensionResponse]
    siguiente_control: ControlPendienteResponse | None
    pendientes: list[ControlPendienteResponse]
    respondidos: list[ControlRespondidoResponse]
