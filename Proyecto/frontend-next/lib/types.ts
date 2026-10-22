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
