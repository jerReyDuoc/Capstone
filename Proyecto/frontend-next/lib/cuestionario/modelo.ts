/**
 * HU-01 / HU-02 · Modelo del cuestionario adaptativo (lógica pura, probada en tests/).
 *
 * Contratos de FastAPI que consume (siempre vía el BFF /bff/api/*):
 *   GET  /api/evaluaciones/{id}/filtro               → EstadoFiltroApi
 *   POST /api/evaluaciones/{id}/filtro               → { controles_aplicables, codigos_controles }
 *   GET  /api/evaluaciones/{id}/controles-aplicables → ControlAplicableApi[]
 *   GET  /api/evaluaciones/{id}/progreso             → ProgresoApi
 *   POST /api/respuestas/  (upsert)                  → { id_respuesta, creada, actualizada }
 *   GET  /api/respuestas/{id}                        → RespuestaDetalleApi
 *   POST /api/respuestas/{id}/evidencias  (multipart)→ 202 { id_evidencia, estado_validacion }
 *   GET  /api/evidencias/{id}                        → EvidenciaApi
 *   POST /api/evaluaciones/{id}/completar            → resumen + estado_progreso
 *
 * Fuente: Proyecto/backend/app/api/routes/{filtro,respuestas,evidencias,reportes}.py
 */

/* ------------------------------------------------------------------ filtro F1–F7 */

export interface PreguntaFiltroApi {
  id_pregunta: number;
  codigo: string; // "F1".."F7"
  orden: number;
  pregunta: string;
  descripcion: string | null;
}

export interface EstadoFiltroApi {
  evaluacion_id: number;
  filtro_completado: boolean;
  fecha_filtro: string | null;
  preguntas: PreguntaFiltroApi[];
  respuestas: { id_respuesta_filtro: number; pregunta_id: number; respuesta: boolean; fecha_respuesta: string }[];
  controles_aplicables: number;
}

export interface FiltroGuardadoApi {
  evaluacion_id: number;
  filtro_completado: true;
  controles_aplicables: number;
  codigos_controles: string[];
}

/** La compuerta raíz: si es NO, no aplica ningún control (control_tree.py). */
export const PREGUNTA_RAIZ = "F1";

/**
 * Espejo de backend/app/application/filters/control_tree.py SOLO para la vista previa
 * mientras se responde ("esta respuesta suma 4 controles"). El número que cuenta es el
 * que devuelve el backend al guardar el filtro; si cambian el árbol allá, actualizar aquí
 * (tests/cuestionario.test.ts compara los totales conocidos).
 */
export const CONTROLES_BASE = 22;
export const CONTROLES_POR_FILTRO: Record<string, number> = { F2: 2, F3: 4, F4: 4, F5: 3, F6: 3, F7: 2 };

export function controlesEstimados(respuestas: Record<string, boolean | undefined>): number {
  if (respuestas[PREGUNTA_RAIZ] !== true) return 0;
  return Object.entries(CONTROLES_POR_FILTRO).reduce(
    (total, [codigo, n]) => total + (respuestas[codigo] === true ? n : 0),
    CONTROLES_BASE,
  );
}

/**
 * Preguntas que hay que mostrar según lo respondido: si F1 es NO, el resto no se pregunta
 * (se envía como NO, porque el backend exige las 7 respuestas).
 */
export function preguntasVisibles(preguntas: PreguntaFiltroApi[], respuestas: Record<string, boolean | undefined>) {
  const ordenadas = [...preguntas].sort((a, b) => a.orden - b.orden);
  if (respuestas[PREGUNTA_RAIZ] === false) return ordenadas.filter((p) => p.codigo === PREGUNTA_RAIZ);
  return ordenadas;
}

/** Cuerpo de POST /filtro: las 7 respuestas; con F1 = NO el resto va en false. */
export function cuerpoFiltro(preguntas: PreguntaFiltroApi[], respuestas: Record<string, boolean | undefined>) {
  const raizNo = respuestas[PREGUNTA_RAIZ] === false;
  return {
    respuestas: preguntas.map((p) => ({
      codigo: p.codigo,
      respuesta: raizNo ? false : respuestas[p.codigo] === true,
    })),
  };
}

/** Respuestas guardadas (por pregunta_id) → mapa por código, para retomar. */
export function respuestasFiltroGuardadas(estado: EstadoFiltroApi): Record<string, boolean> {
  const porId = new Map(estado.preguntas.map((p) => [p.id_pregunta, p.codigo]));
  const mapa: Record<string, boolean> = {};
  for (const r of estado.respuestas) {
    const codigo = porId.get(r.pregunta_id);
    if (codigo) mapa[codigo] = r.respuesta;
  }
  return mapa;
}

/* ------------------------------------------------------------------ controles */

export interface ControlAplicableApi {
  id_control: number;
  codigo_control: string | null;
  framework_fuente: string | null;
  articulo_referencia: string | null;
  tipo_fuente: string | null;
  obligacion: string | null;
  pregunta_evaluacion: string | null;
  aplicabilidad: string | null;
  evidencia_esperada: string | null;
  criticidad: string | null;
  recomendacion: string | null;
  dominio: { id: number; nombre_dominio: string | null } | null;
}

export interface ControlPendienteApi {
  id_control: number;
  codigo_control: string;
  dominio_id: number | null;
  dominio: string | null;
}

export interface ControlRespondidoApi extends ControlPendienteApi {
  id_respuesta: number;
  estado_clasificacion: string | null;
  estado_clasificacion_final: string | null;
}

export interface ProgresoApi {
  evaluacion_id: number;
  estado_progreso: string | null;
  cerrada: boolean;
  filtro_completado: boolean;
  etapa: "filtro" | "cuestionario" | "completo" | "cerrada";
  controles_aplicables: number;
  controles_respondidos: number;
  controles_pendientes: number;
  porcentaje: number;
  por_dimension: { dominio_id: number | null; dominio: string | null; aplicables: number; respondidos: number; porcentaje: number }[];
  siguiente_control: ControlPendienteApi | null;
  pendientes: ControlPendienteApi[];
  respondidos: ControlRespondidoApi[];
}

/** Orden del cuestionario: por dominio (en el orden en que aparecen) y luego por código. */
export function ordenarControles(controles: ControlAplicableApi[]): ControlAplicableApi[] {
  const ordenDominio = new Map<string, number>();
  for (const c of controles) {
    const d = c.dominio?.nombre_dominio ?? "Sin dominio";
    if (!ordenDominio.has(d)) ordenDominio.set(d, ordenDominio.size);
  }
  return [...controles].sort((a, b) => {
    const da = ordenDominio.get(a.dominio?.nombre_dominio ?? "Sin dominio")!;
    const db = ordenDominio.get(b.dominio?.nombre_dominio ?? "Sin dominio")!;
    if (da !== db) return da - db;
    return (a.codigo_control ?? "").localeCompare(b.codigo_control ?? "");
  });
}

/* ------------------------------------------------------------------ respuestas (HU-02) */

export type EstadoDeclarado = "cumplido" | "parcialmente_cumplido" | "no_cumplido" | "no_aplica" | "requiere_revision";

export interface OpcionEstado {
  valor: EstadoDeclarado;
  etiqueta: string;
  ayuda: string;
  tono: "ok" | "medio" | "alto" | "info" | "bajo";
  /** HU-02 C2: justificación obligatoria (≥ JUSTIFICACION_MIN caracteres con letras). */
  justificacionObligatoria: boolean;
  /** Admite evidencia que valida el LLM (cumplido, parcial, requiere revisión). */
  admiteEvidencia: boolean;
  /** Para completar la evaluación, este estado necesita al menos una evidencia. */
  evidenciaObligatoria: boolean;
}

export const ESTADOS: OpcionEstado[] = [
  {
    valor: "cumplido",
    etiqueta: "Cumplido",
    ayuda: "El control está implementado y se puede demostrar.",
    tono: "ok",
    justificacionObligatoria: false,
    admiteEvidencia: true,
    evidenciaObligatoria: false,
  },
  {
    valor: "parcialmente_cumplido",
    etiqueta: "Parcialmente cumplido",
    ayuda: "Hay avances, pero falta formalizarlo o cubrir todos los casos.",
    tono: "medio",
    justificacionObligatoria: true,
    admiteEvidencia: true,
    evidenciaObligatoria: false,
  },
  {
    valor: "no_cumplido",
    etiqueta: "No cumplido",
    ayuda: "El control no existe hoy en la organización.",
    tono: "alto",
    justificacionObligatoria: false,
    admiteEvidencia: false,
    evidenciaObligatoria: false,
  },
  {
    valor: "requiere_revision",
    etiqueta: "Requiere revisión",
    ayuda: "¿No estás seguro? Adjunta una evidencia y la IA decidirá si se cumple, se cumple en parte o no.",
    tono: "info",
    justificacionObligatoria: true,
    admiteEvidencia: true,
    evidenciaObligatoria: true,
  },
  {
    valor: "no_aplica",
    etiqueta: "No aplica",
    ayuda: "Este control no corresponde a la realidad de la organización.",
    tono: "bajo",
    justificacionObligatoria: false,
    admiteEvidencia: false,
    evidenciaObligatoria: false,
  },
];

export const ESTADO_POR_VALOR = Object.fromEntries(ESTADOS.map((e) => [e.valor, e])) as Record<EstadoDeclarado, OpcionEstado>;

export const esEstadoDeclarado = (v: unknown): v is EstadoDeclarado =>
  typeof v === "string" && Object.prototype.hasOwnProperty.call(ESTADO_POR_VALOR, v);

/** Igual que JUSTIFICACION_MIN_CARACTERES del backend (app/core/config.py). */
export const JUSTIFICACION_MIN = 20;
export const JUSTIFICACION_MAX = 2000;

export function normalizarJustificacion(texto: string): string {
  return texto.replace(/\s+/g, " ").trim();
}

/** Mismo criterio que validar_justificacion() del backend; null si es válida. */
export function errorJustificacion(estado: EstadoDeclarado, texto: string): string | null {
  const limpio = normalizarJustificacion(texto);
  if (limpio.length > JUSTIFICACION_MAX) return `La justificación no puede superar ${JUSTIFICACION_MAX} caracteres.`;
  if (!ESTADO_POR_VALOR[estado].justificacionObligatoria) return null;
  if (limpio.length < JUSTIFICACION_MIN || !/\p{L}/u.test(limpio)) {
    return `Explica en al menos ${JUSTIFICACION_MIN} caracteres por qué el control queda en este estado (llevas ${limpio.length}).`;
  }
  return null;
}

export interface RespuestaGuardadaApi {
  id_respuesta: number;
  creada: boolean;
  actualizada: boolean;
}

export interface EvidenciaApi {
  id_evidencia: number;
  nombre_archivo: string;
  estado_validacion: "pending" | "processing" | "validated" | "rejected" | "error" | string;
  clasificacion_llm: string | null;
  confianza: number | null;
  justificacion_llm: string | null;
  errores_validacion: unknown[] | null;
  fecha_subida: string | null;
  fecha_procesada: string | null;
}

export interface RespuestaDetalleApi {
  id_respuesta: number;
  estado_clasificacion: string | null;
  justificacion_usuario: string | null;
  estado_clasificacion_final: string | null;
  fuente_clasificacion: string | null;
  confianza_clasificacion: number | null;
  fecha_validacion: string | null;
  evidencias: EvidenciaApi[];
}

export const evidenciaEnCurso = (e: Pick<EvidenciaApi, "estado_validacion">) =>
  e.estado_validacion === "pending" || e.estado_validacion === "processing";

export const ESTADO_EVIDENCIA: Record<string, { etiqueta: string; tono: OpcionEstado["tono"] }> = {
  pending: { etiqueta: "En cola", tono: "info" },
  processing: { etiqueta: "Validando con IA", tono: "info" },
  validated: { etiqueta: "Validada", tono: "ok" },
  rejected: { etiqueta: "No respalda el control", tono: "alto" },
  error: { etiqueta: "No se pudo validar", tono: "medio" },
};

/**
 * Formatos de evidencia. El worker (process_evidence.py) lee el archivo como texto UTF-8,
 * así que hoy solo los formatos de texto se validan bien; un PDF o un Word llegarían
 * como bytes ilegibles al LLM. Ampliar esta lista cuando el backend extraiga texto de PDF.
 */
export const EXTENSIONES_EVIDENCIA = [".txt", ".md", ".csv", ".json"];
export const MAX_BYTES_EVIDENCIA = 12 * 1024 * 1024; // igual que MAX_BYTES_ARCHIVO del BFF

export function errorArchivoEvidencia(archivo: { name: string; size: number }): string | null {
  const nombre = archivo.name.toLowerCase();
  if (!EXTENSIONES_EVIDENCIA.some((ext) => nombre.endsWith(ext))) {
    return `Por ahora la evidencia debe ser un archivo de texto (${EXTENSIONES_EVIDENCIA.join(", ")}).`;
  }
  if (archivo.size === 0) return "El archivo está vacío.";
  if (archivo.size > MAX_BYTES_EVIDENCIA) return "El archivo supera el máximo de 12 MB.";
  return null;
}

/* ------------------------------------------------------------------ revisión antes de completar */

export interface Bloqueo {
  tipo: "pendiente" | "revision-sin-evidencia" | "evidencia-en-curso";
  idControl: number;
  codigo: string;
}

/**
 * Lo mismo que exige CompletarEvaluacionUseCase, calculado en el navegador para avisar
 * ANTES de llamar a /completar (el backend lo vuelve a verificar).
 */
export function bloqueosParaCompletar(
  progreso: Pick<ProgresoApi, "pendientes" | "respondidos">,
  evidencias: Map<number, EvidenciaApi[]>, // por id_respuesta
): Bloqueo[] {
  const bloqueos: Bloqueo[] = progreso.pendientes.map((p) => ({ tipo: "pendiente", idControl: p.id_control, codigo: p.codigo_control }));
  for (const r of progreso.respondidos) {
    const ev = evidencias.get(r.id_respuesta) ?? [];
    if (ev.some(evidenciaEnCurso)) {
      bloqueos.push({ tipo: "evidencia-en-curso", idControl: r.id_control, codigo: r.codigo_control });
    }
    if (r.estado_clasificacion === "requiere_revision" && ev.length === 0) {
      bloqueos.push({ tipo: "revision-sin-evidencia", idControl: r.id_control, codigo: r.codigo_control });
    }
  }
  return bloqueos;
}
