/* ------------------------------------------------------------------
 * Contratos del backend (FastAPI) que consume el panel.
 * Fuente: Proyecto/backend/app/api/routes/{reportes,evaluaciones,catalogos}.py
 * ------------------------------------------------------------------ */

export type NivelMadurez = "inicial" | "en_desarrollo" | "gestionado" | "optimizado";

export type EstadoClasificacion =
  | "cumplido"
  | "parcialmente_cumplido"
  | "no_cumplido"
  | "no_aplica"
  | "requiere_revision";

/** GET /api/evaluaciones */
export interface EvaluacionApi {
  id: number;
  fecha_inicio: string | null;
  estado_progreso: string | null;
  usuario_temporal_id: number | null;
}

export interface Paginado<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/** GET /api/evaluaciones/{id}/resumen */
export interface ResumenApi {
  evaluacion_id: number;
  puntaje_general: number;
  nivel_madurez_general: NivelMadurez;
  total_controles_evaluados: number;
  dominios: {
    dominio_id: number;
    dominio: string;
    puntaje: number | null;
    nivel_madurez: NivelMadurez | null;
    total_controles_evaluados: number | null;
  }[];
}

/** GET /api/evaluaciones/{id}/comparativa */
export interface ComparativaApi {
  evaluacion_id: number;
  rubro_id: number | null;
  /** HU-12/HU-13: lo que debería alcanzar cada dimensión (META_CUMPLIMIENTO_PUNTAJE). Backends previos no lo traen. */
  meta_puntaje?: number;
  meta_nivel?: NivelMadurez;
  /** Evaluaciones del rubro necesarias para mostrar su promedio (COMPARATIVA_MIN_MUESTRAS). */
  muestras_minimas?: number;
  comparativas: {
    dominio: string;
    tu_puntaje: number | null;
    tu_nivel: NivelMadurez | null;
    promedio_industria: number | null;
    mediana_industria: number | null;
    maximo_industria: number | null;
    minimo_industria: number | null;
    muestras: number;
    referencia_suficiente?: boolean;
    diferencia_vs_promedio: number | null;
    meta?: number;
    diferencia_vs_meta?: number;
    cumple_meta?: boolean;
  }[];
}

/** GET /api/evaluaciones/{id}/respuestas */
export interface RespuestaApi {
  id_respuesta: number;
  estado_clasificacion: EstadoClasificacion | null;
  estado_clasificacion_final: EstadoClasificacion | null;
  fuente_clasificacion: string | null;
  confianza_clasificacion: number | null;
  fecha_validacion: string | null;
  matriz_controles_id_control: number | null;
  catalogo_brechas_id_brecha: number | null;
}

/** GET /api/brechas */
export interface BrechaCatalogoApi {
  id_brecha: number;
  codigo_brecha: string | null;
  categoria: string | null;
  comportamiento_detectado: string | null;
  criticidad: string | null;
  accion_sistema: string | null;
  ruta_formativa: { id: number; nombre: string | null } | null;
}

/** GET /api/controles (HU-11: respaldo de criticidad, código y dominio del control) */
export interface ControlApi {
  id_control: number;
  codigo_control: string | null;
  obligacion: string | null;
  criticidad: string | null;
  recomendacion: string | null;
  dominio: { id: number; nombre_dominio: string | null } | null;
}

/* ------------------------------------------------------------------
 * Modelo de vista: lo que dibujan los componentes.
 * ------------------------------------------------------------------ */

/** Impacto del control según el catálogo (Alta/Media/Baja). */
export type Criticidad = "Alta" | "Media" | "Baja" | "Sin clasificar";

/**
 * HU-11 · Severidad de la brecha = impacto del control × qué tan incumplido está.
 * Es la que ordena el listado priorizado (ver lib/severidad.ts).
 */
export type Severidad = "Crítica" | "Alta" | "Media" | "Baja" | "Sin clasificar";

export type EstadoBrecha = "no_cumplido" | "parcialmente_cumplido";

export interface DominioVista {
  id: number | null;
  nombre: string;
  puntaje: number;              // 0-100
  nivel: NivelMadurez;
  controles: number;
  promedioIndustria: number | null;
  diferencia: number | null;    // puntos vs. promedio de la industria
  muestras: number;
  /** Puntaje que debería alcanzar la dimensión y cuánto le falta (negativo) o sobra. */
  meta: number;
  diferenciaMeta: number;
}

export interface BrechaVista {
  respuestaId: number;
  codigo: string;
  dominio: string;
  descripcion: string;
  /** Impacto del control (catálogo de brechas o, en su defecto, matriz de controles). */
  criticidad: Criticidad;
  /** HU-11: severidad resultante de la matriz impacto × estado. */
  severidad: Severidad;
  /** HU-11: posición en el listado priorizado (1 = la más urgente). Estable aunque se filtre. */
  prioridad: number;
  estado: EstadoBrecha;
  accion: string | null;
  rutaFormativa: string | null;
  controlId: number | null;
  controlCodigo: string | null;
  /** Puntaje 0-100 del dominio de la brecha (desempate: dominio menos maduro primero). */
  puntajeDominio: number | null;
}

export interface PanelVista {
  evaluacionId: number;
  puntajeGeneral: number;
  nivelGeneral: NivelMadurez;
  controlesEvaluados: number;
  enRevision: number;
  dominios: DominioVista[];
  brechas: BrechaVista[];
  brechasPorCriticidad: Record<Criticidad, number>;
  /** HU-11 */
  brechasPorSeveridad: Record<Severidad, number>;
  noCumplidos: number;
  parciales: number;
  tieneBenchmark: boolean;
  /** Meta de cumplimiento por dimensión (0-100). */
  meta: number;
  /** Evaluaciones del rubro necesarias para mostrar su promedio, y las que hay hoy (máx. entre dominios). */
  muestrasMinimas: number;
  muestrasRubro: number;
  /** El backend no tiene rubro para esta evaluación o falló la comparativa. */
  sinRubro: boolean;
}

/* ------------------------------------------------------------------
 * HU-12 · Plan formativo (GET /api/evaluaciones/{id}/plan-formativo)
 * ------------------------------------------------------------------ */

export type NivelFormativo = "Inicial" | "Intermedio" | "Avanzado";

export interface RutaPlanApi {
  id: number;
  nombre: string;
  dominio: string | null;
  nivel: NivelFormativo | null;
  objetivo: string | null;
  objetivos_especificos: string[];
  contenidos: string[];
  horas: number | null;
  modalidad: string | null;
  publico_objetivo: string | null;
}

export interface BrechaCubiertaApi {
  codigo: string;
  control_codigo: string | null;
  dominio: string;
  severidad: Severidad;
  estado: EstadoBrecha;
  prioridad: number;
  /** HU-17/HU-26: respuesta de la brecha (enlaza con "subir evidencia"). Backends previos no lo traen. */
  respuesta_id?: number | null;
}

export interface ModuloPlanApi {
  nivel: NivelFormativo;
  /** "brechas": lo activó una brecha · "nivel": base del nivel asignado a la dimensión. */
  motivo: "brechas" | "nivel";
  prioridad: Severidad | "Complementario";
  ruta: RutaPlanApi;
  brechas: BrechaCubiertaApi[];
}

export interface DimensionPlanApi {
  dominio_id: number | null;
  dominio: string;
  puntaje: number | null;
  nivel_madurez: NivelMadurez | null;
  nivel_asignado: NivelFormativo;
  objetivo_nivel: string;
  brechas: number;
  horas: number;
  modulos: ModuloPlanApi[];
}

export interface PlanFormativoApi {
  evaluacion_id: number;
  resumen: {
    dimensiones: number;
    modulos: number;
    horas: number;
    brechas_total: number;
    brechas_mapeadas: number;
    cobertura_mapeo: number;
  };
  brechas_sin_ruta: BrechaCubiertaApi[];
  dimensiones: DimensionPlanApi[];
}

/* ------------------------------------------------------------------
 * HU-26 · Recorrido de módulos y avance formativo de la empresa
 * Fuente: Proyecto/backend/app/api/routes/formacion.py
 * ------------------------------------------------------------------ */

export type EstadoModulo = "no_iniciado" | "en_curso" | "completado";

export interface ModuloAvanceApi {
  ruta_id: number;
  nombre: string;
  dominio: string;
  nivel: NivelFormativo;
  horas: number | null;
  modalidad: string | null;
  /** "historial": ya no está en el plan (su brecha se cerró con evidencia) pero la empresa lo hizo. */
  motivo: "brechas" | "nivel" | "historial";
  prioridad: Severidad | "Complementario";
  en_plan: boolean;
  estado: EstadoModulo;
  lecciones_total: number;
  lecciones_vistas: number;
  porcentaje_lecciones: number;
  intentos: number;
  mejor_puntaje: number | null;
  fecha_inicio: string | null;
  fecha_completado: string | null;
  codigo_constancia: string | null;
  brechas: string[];
}

export interface GrupoAvanceApi {
  total: number;
  completados: number;
  en_curso: number;
  porcentaje: number;
  horas_total: number;
  horas_completadas: number;
}

export interface BrechaFormacionApi {
  codigo: string;
  respuesta_id: number | null;
  control_codigo: string | null;
  dominio: string;
  severidad: Severidad;
  estado: EstadoBrecha;
  prioridad: number;
  ruta_id: number;
  modulo: string;
  formacion_completada: boolean;
}

/** GET /api/formacion/avance */
export interface AvanceFormativoApi {
  evaluacion_id: number;
  empresa: { id: number; razon_social: string };
  umbral_aprobacion: number;
  resumen: {
    modulos_total: number;
    iniciados: number;
    en_curso: number;
    completados: number;
    porcentaje: number;
    horas_total: number;
    horas_completadas: number;
    brechas_total: number;
    brechas_con_formacion: number;
    porcentaje_brechas_con_formacion: number;
  };
  por_dimension: (GrupoAvanceApi & { dominio: string })[];
  por_nivel: (GrupoAvanceApi & { nivel: NivelFormativo })[];
  modulos: ModuloAvanceApi[];
  brechas: BrechaFormacionApi[];
}

export interface MaterialApoyoApi {
  tipo: string;
  titulo: string;
  descripcion?: string;
}

export interface LeccionApi {
  orden: number;
  titulo: string;
  resumen: string | null;
  contenido: string[];
  material_apoyo: MaterialApoyoApi[];
  duracion_min: number | null;
  vista: boolean;
}

export interface PreguntaActividadApi {
  id: number;
  orden: number;
  enunciado: string;
  /** `id` es lo que se envía al corregir; el orden en pantalla lo baraja el servidor. */
  opciones: { id: number; texto: string }[];
}

export interface AvanceModuloApi {
  estado: EstadoModulo;
  lecciones_vistas: number[];
  intentos: number;
  mejor_puntaje: number | null;
  ultimo_puntaje: number | null;
  fecha_inicio: string | null;
  fecha_completado: string | null;
  codigo_constancia: string | null;
  porcentaje_lecciones: number;
}

/** GET /api/formacion/modulos/{ruta_id} */
export interface ModuloRecorridoApi {
  evaluacion_id: number;
  ruta: {
    id: number;
    nombre: string;
    dominio: string | null;
    nivel: NivelFormativo | null;
    objetivo: string | null;
    objetivos_especificos: string[];
    horas: number | null;
    modalidad: string | null;
    publico_objetivo: string | null;
  };
  en_plan: boolean;
  motivo: "brechas" | "nivel" | "historial";
  prioridad: Severidad | "Complementario";
  brechas: { codigo: string; respuesta_id: number | null; control_codigo: string | null; dominio: string; severidad: Severidad; estado: EstadoBrecha }[];
  lecciones: LeccionApi[];
  actividad: {
    preguntas: PreguntaActividadApi[];
    umbral_aprobacion: number;
    intentos_por_dia: number;
    intentos_restantes_hoy: number | null;
    disponible: boolean;
  };
  avance: AvanceModuloApi;
  dimension_nivel: NivelFormativo | null;
}

/** POST /api/formacion/modulos/{ruta_id}/verificacion */
export interface ResultadoVerificacionApi {
  aprobado: boolean;
  puntaje: number;
  correctas: number;
  total: number;
  umbral_aprobacion: number;
  detalle: { pregunta_id: number; correcta: boolean; explicacion?: string | null }[];
  sin_responder: number[];
  intentos_restantes_hoy: number;
  avance: AvanceModuloApi;
}

/* ------------------------------------------------------------------
 * HU-17 · Remediación: re-evaluar un control con evidencia nueva
 * Fuente: Proyecto/backend/app/api/routes/remediacion.py
 * ------------------------------------------------------------------ */

export interface TerminosControlApi {
  terminos: string[];
  encontrados: string[];
  faltantes: string[];
  cobertura: number | null;
  /** HU-17 C2 · RAG local: presente cuando el documento no cabía completo y se usaron sus pasajes más relevantes. */
  rag?: { aplicado: boolean; pasajes_total: number | null; pasajes_usados: number | null; pasajes_con_terminos?: number };
}

export interface EvidenciaRemediacionApi {
  id_evidencia: number;
  respuesta_id: number;
  nombre_archivo: string;
  estado_validacion: "pending" | "processing" | "validated" | "rejected" | "error";
  estado_declarado: EstadoClasificacion | null;
  estado_previo: EstadoClasificacion | null;
  estado_resultante: EstadoClasificacion | null;
  clasificacion_llm: EstadoClasificacion | null;
  confianza: number | null;
  justificacion_llm: string | null;
  errores_validacion: string[];
  terminos_control: TerminosControlApi | null;
  fecha_subida: string | null;
  fecha_procesada: string | null;
  en_proceso: boolean;
  mejoro: boolean;
  /** Puntaje general antes y después de procesarla (iguales si el control no mejoró). */
  puntaje_previo?: number | null;
  puntaje_resultante?: number | null;
  /** Solo en GET /evidencias/{id} */
  estado_actual?: EstadoClasificacion;
  puntaje_general?: number | null;
  dominios?: { dominio: string; puntaje: number | null }[];
}

export interface ControlRemediacionApi {
  respuesta_id: number;
  control_codigo: string | null;
  codigo_brecha: string | null;
  dominio: string | null;
  estado: "no_cumplido" | "parcialmente_cumplido" | "requiere_revision";
  severidad: Severidad;
  obligacion: string | null;
  pregunta: string | null;
  evidencia_esperada: string | null;
  recomendacion: string | null;
  ruta: { id: number; nombre: string } | null;
  formacion_completada: boolean;
  ultima_evidencia: EvidenciaRemediacionApi | null;
  /** Intentos anteriores, del más nuevo al más antiguo. */
  historial?: EvidenciaRemediacionApi[];
}

/** GET /api/remediacion/evaluaciones/{id} */
export interface RemediacionApi {
  evaluacion_id: number;
  puntaje_general: number;
  /** Puntaje antes de la primera remediación que lo mejoró (o el actual si no hay ninguna). */
  puntaje_inicial?: number;
  evolucion?: { fecha: string | null; antes: number; despues: number }[];
  controles_mejorados?: number;
  dominios: { dominio: string; puntaje: number | null }[];
  controles: ControlRemediacionApi[];
  tipos_admitidos: string[];
  max_mb: number;
  evidencias_por_dia: number;
}

/* ------------------------------------------------------------------
 * HU-15 · Agente IA Tutor (GET/POST /api/tutor/*)
 * ------------------------------------------------------------------ */

export type TipoMensajeTutor = "pregunta" | "explicacion" | "plan_accion" | "orientacion" | "fuera_de_alcance" | "bloqueado";

/** Brecha del contexto aislado del tutor (solo catálogo y control; sin datos de la empresa). */
export interface BrechaTutorApi {
  ref: string;
  codigo: string;
  control_codigo: string | null;
  dominio: string;
  descripcion: string;
  severidad: Severidad;
  estado: "no_cumplido" | "parcialmente_cumplido";
  accion: string | null;
  prioridad: number;
  respuesta_id: number;
  ruta_id: number | null;
  ruta_nombre: string | null;
  ruta_nivel: NivelFormativo | null;
  formacion_completada: boolean;
  /** v1.1: framework y artículo reales del control (de la matriz). */
  fuente_normativa?: string | null;
}

export interface CuotaTutorApi {
  usados: number;
  limite: number | null;
  restantes: number | null;
  reinicia_en: string;
}

/** GET /api/tutor/contexto */
export interface ContextoTutorApi {
  evaluacion_id: number;
  fecha_evaluacion: string | null;
  puntaje_general: number | null;
  nivel_madurez: string | null;
  nivel_sugerido: NivelFormativo;
  brechas_total: number;
  brechas_por_estado: Record<string, number>;
  brechas_por_severidad: Record<string, number>;
  brechas: BrechaTutorApi[];
  foco: { ruta_id: number; nombre: string; nivel: NivelFormativo | null } | null;
  niveles: NivelFormativo[];
  cuota?: CuotaTutorApi;
  max_caracteres?: number;
}

export interface ConversacionTutorApi {
  id: number;
  titulo: string | null;
  nivel: NivelFormativo;
  evaluacion_id: number;
  ruta_id: number | null;
  mensajes_total: number;
  fecha_creacion: string | null;
  fecha_ultimo_mensaje: string | null;
  /** "solo_lectura": es de una evaluación anterior de la empresa. */
  estado: "activa" | "solo_lectura";
}

export interface PasoTutorApi {
  orden: number;
  accion: string;
  responsable_sugerido: string | null;
  evidencia_esperada: string | null;
}

export interface BrechaCitadaApi {
  ref: string;
  codigo: string;
  dominio: string;
  severidad: Severidad;
  estado: string;
  ruta_id: number | null;
  respuesta_id: number;
}

export interface MensajeTutorApi {
  id: number;
  rol: "usuario" | "tutor";
  tipo: TipoMensajeTutor;
  contenido: string;
  nivel: NivelFormativo | null;
  bloqueado: boolean;
  fecha: string | null;
  pasos: PasoTutorApi[];
  brechas: BrechaCitadaApi[];
  referencias_normativas: string[];
  sugerencias: string[];
}

export interface ListaConversacionesApi {
  evaluacion_vigente: number | null;
  items: ConversacionTutorApi[];
}

export interface ConversacionDetalleApi {
  conversacion: ConversacionTutorApi;
  mensajes: MensajeTutorApi[];
  cuota?: CuotaTutorApi;
}

/** POST /api/tutor/conversaciones/{id}/mensajes */
export interface RespuestaTutorApi {
  mensaje_usuario: MensajeTutorApi;
  respuesta: MensajeTutorApi;
  conversacion: ConversacionTutorApi;
  cuota: CuotaTutorApi;
}
