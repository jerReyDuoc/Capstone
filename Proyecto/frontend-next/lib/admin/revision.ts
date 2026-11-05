/**
 * HU-22 · Bandeja de revisión del Oficial de Cumplimiento (panel interno).
 *
 * Contratos de FastAPI /api/admin/revision/* (app/api/routes/admin_revision.py) y de las dos
 * decisiones: PATCH /api/respuestas/{id}/revision y PATCH /api/seguridad/eventos/{id}/revision.
 * La lógica pura (textos, decisión confirmar/corregir, validación del comentario, filtros en la
 * URL) se prueba en tests/hu22_revision.test.ts.
 *
 * Pantalla interna: aquí sí se ven los códigos de control (DAT-001), porque el oficial trabaja
 * con ellos. El cliente nunca los ve.
 */
import { pedir } from "@/lib/encuesta/cliente";

export type Clasificacion = "cumplido" | "parcialmente_cumplido" | "no_cumplido" | "no_aplica" | "requiere_revision";
export type Resolutiva = Exclude<Clasificacion, "requiere_revision">;
export type Motivo = "seguridad" | "divergencia" | "sin_resolver" | "baja_confianza" | "resuelta_por_llm" | "concordante";
export type EstadoRevision = "pendiente" | "revisada" | "todas";
export type Vista = "clasificaciones" | "eventos";
export type Resolucion = "ataque_confirmado" | "falso_positivo";
export type Decision = "confirmada" | "corregida";

export interface ItemRespuesta {
  tipo_item: "respuesta";
  id: number;
  evaluacion: {
    id: number | null; origen: string | null; estado_progreso: string | null; cerrada: boolean;
    es_prueba: boolean; empresa: string | null;
  };
  control: {
    id: number | null; codigo: string | null; pregunta: string | null; criticidad: string | null;
    dominio_id: number | null; dominio: string | null;
    obligacion?: string | null; evidencia_esperada?: string | null; articulo_referencia?: string | null;
  };
  declarado: Clasificacion | null;
  estado_final: Clasificacion | null;
  fuente: string | null;
  llm: { clasificacion: Clasificacion | null; confianza: number | null; fecha: string | null; evidencia_id: number; bajo_umbral: boolean } | null;
  motivos: Motivo[];
  eventos_seguridad: number;
  pendiente: boolean;
  revision: { clasificacion: Resolutiva; decision: Decision | null; fecha: string | null; comentario: string | null; vigente: boolean } | null;
  fecha_referencia: string | null;
}

export interface ItemEvento {
  tipo_item: "evento";
  id: number;
  fecha: string | null;
  tipo: string;
  origen: string;
  evaluacion_id: number | null;
  respuesta_id: number | null;
  evidencia_id: number | null;
  control: { id: number | null; codigo: string | null; pregunta: string | null } | null;
  extracto: string | null;
  pendiente: boolean;
  revision: { resolucion: Resolucion | null; comentario: string | null; fecha: string | null } | null;
}

export interface EvidenciaDetalle {
  id: number; nombre_archivo: string; origen: string; estado_validacion: string; estado_declarado: string | null;
  clasificacion_llm: Clasificacion | null; confianza: number | null; justificacion_llm: string | null;
  errores: string[]; fecha_subida: string | null; fecha_procesada: string | null; eliminada: boolean;
}

export interface PasoHistorial {
  audit_id: number; fecha: string | null; actor_rol: string; actor_id: number | null; revisor: string | null;
  anterior: Clasificacion | null; nueva: Clasificacion | null; decision: Decision | null;
  clasificacion_llm: Clasificacion | null; con_comentario: boolean;
}

export interface DetalleRespuesta extends ItemRespuesta {
  justificacion_usuario: string | null;
  evidencias: EvidenciaDetalle[];
  eventos: ItemEvento[];
  historial: PasoHistorial[];
  opciones: Resolutiva[];
}

export interface Bandeja<T = ItemRespuesta | ItemEvento> {
  vista: Vista; estado: EstadoRevision; motivo: Motivo | null;
  items: T[]; total: number; page: number; size: number; pages: number;
  pendientes: { clasificaciones: number; eventos: number; por_motivo: Record<Motivo, number> };
  umbral_confianza: number;
}

export interface ResumenReferencia {
  revisadas: number; confirmadas: number; corregidas: number;
  precision_llm: { n_revisadas: number; accuracy: number | null; tasa_error_modelo: number | null; f1_macro: number | null };
  eventos: { ataques_confirmados: number; falsos_positivos: number; sin_veredicto: number; precision_deteccion: number | null };
  umbral_confianza: number;
}

export interface FiltrosBandeja {
  vista: Vista;
  estado: EstadoRevision;
  motivo: Motivo | null;
  evaluacion_id: number | null;
  dominio_id: number | null;
  criticidad: string | null;
  orden: "prioridad" | "reciente";
  page: number;
}

export const FILTROS_INICIALES: FiltrosBandeja = {
  vista: "clasificaciones", estado: "pendiente", motivo: null, evaluacion_id: null,
  dominio_id: null, criticidad: null, orden: "prioridad", page: 1,
};

export const TAMANO_PAGINA = 25;

/** Query string para FastAPI (solo lo que no es el valor por defecto; el BFF filtra el resto). */
export function queryBandeja(f: FiltrosBandeja): string {
  const p = new URLSearchParams();
  p.set("vista", f.vista);
  p.set("estado", f.estado);
  if (f.vista === "clasificaciones") {
    if (f.motivo) p.set("motivo", f.motivo);
    if (f.dominio_id) p.set("dominio_id", String(f.dominio_id));
    if (f.criticidad) p.set("criticidad", f.criticidad);
    if (f.orden !== "prioridad") p.set("orden", f.orden);
  }
  if (f.evaluacion_id) p.set("evaluacion_id", String(f.evaluacion_id));
  if (f.page > 1) p.set("page", String(f.page));
  p.set("size", String(TAMANO_PAGINA));
  return p.toString();
}

const BASE = "/bff/admin/api";

export const apiRevision = {
  bandeja: (f: FiltrosBandeja) => pedir<Bandeja>(`${BASE}/admin/revision/bandeja?${queryBandeja(f)}`),
  detalle: (id: number) => pedir<DetalleRespuesta>(`${BASE}/admin/revision/respuestas/${id}`),
  resumen: () => pedir<ResumenReferencia>(`${BASE}/admin/revision/resumen`),
  dominios: () => pedir<{ id: number; nombre_dominio: string | null }[]>(`${BASE}/dominios`),
  revisarRespuesta: (id: number, clasificacion_revisada: Resolutiva, comentario: string) =>
    pedir<{ decision: Decision; estado_clasificacion_final: Resolutiva; puntajes_recalculados: boolean }>(
      `${BASE}/respuestas/${id}/revision`,
      { method: "PATCH", json: { clasificacion_revisada, comentario } },
    ),
  revisarEvento: (id: number, resolucion: Resolucion, comentario: string) =>
    pedir<ItemEvento>(`${BASE}/seguridad/eventos/${id}/revision`, { method: "PATCH", json: { resolucion, comentario } }),
};

// --------------------------------------------------------------------- textos
export const RESOLUTIVAS: Resolutiva[] = ["cumplido", "parcialmente_cumplido", "no_cumplido", "no_aplica"];

export const NOMBRE_CLASIFICACION: Record<Clasificacion, string> = {
  cumplido: "Cumplido",
  parcialmente_cumplido: "Parcialmente cumplido",
  no_cumplido: "No cumplido",
  no_aplica: "No aplica",
  requiere_revision: "Requiere revisión",
};

/** Tono (clases globales tone-*) de cada clasificación. */
export const TONO_CLASIFICACION: Record<Clasificacion, string> = {
  cumplido: "ok",
  parcialmente_cumplido: "medio",
  no_cumplido: "alto",
  no_aplica: "info",
  requiere_revision: "medio",
};

export const MOTIVOS: Motivo[] = ["seguridad", "divergencia", "sin_resolver", "baja_confianza", "resuelta_por_llm", "concordante"];

export const TEXTO_MOTIVO: Record<Motivo, { corto: string; ayuda: string }> = {
  seguridad: {
    corto: "Bloqueo de seguridad",
    ayuda: "La capa de seguridad detectó un posible intento de manipular a la IA en la justificación o en una evidencia.",
  },
  divergencia: {
    corto: "La IA no coincide",
    ayuda: "La IA propuso una clasificación distinta de la que declaró la organización.",
  },
  sin_resolver: {
    corto: "Sin resolver",
    ayuda: "La pregunta sigue en «Requiere revisión»: nadie la ha cerrado y hoy puntúa 0.",
  },
  baja_confianza: {
    corto: "IA con baja confianza",
    ayuda: "La IA respondió con poca certeza, así que se mantuvo lo declarado por la organización.",
  },
  resuelta_por_llm: {
    corto: "Decidida por la IA",
    ayuda: "La organización no supo clasificarla y la IA la cerró con su evidencia.",
  },
  concordante: {
    corto: "La IA coincide",
    ayuda: "La IA respaldó lo declarado. Revisar algunas sirve para medir también sus aciertos.",
  },
};

export const TONO_MOTIVO: Record<Motivo, string> = {
  seguridad: "alto",
  divergencia: "medio",
  sin_resolver: "medio",
  baja_confianza: "info",
  resuelta_por_llm: "info",
  concordante: "ok",
};

export const NOMBRE_ORIGEN_EVENTO: Record<string, string> = {
  justificacion: "Justificación del cuestionario",
  evidencia: "Evidencia del cuestionario",
  tutor: "Mensaje al Tutor IA",
  tutor_antecedente: "Antecedente omitido por el Tutor IA",
  borrador: "Instrucciones de un borrador",
};

export const NOMBRE_RESOLUCION: Record<Resolucion, string> = {
  ataque_confirmado: "Ataque confirmado",
  falso_positivo: "Falso positivo",
};

export const nombreClasificacion = (c: string | null | undefined) =>
  c && c in NOMBRE_CLASIFICACION ? NOMBRE_CLASIFICACION[c as Clasificacion] : "Sin clasificar";

export const porcentaje = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)} %`);

export function fechaCorta(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("es-CL", { day: "numeric", month: "short", year: "numeric" });
}

// --------------------------------------------------------------------- decisión
export const COMENTARIO_MIN = 10;
export const COMENTARIO_MAX = 1000;

/** Igual que el backend: los espacios repetidos no cuentan. */
export const largoComentario = (t: string) => t.split(/\s+/).filter(Boolean).join(" ").length;

export function errorComentario(texto: string): string | null {
  const n = largoComentario(texto);
  if (n < COMENTARIO_MIN) return `Explica tu decisión en al menos ${COMENTARIO_MIN} caracteres.`;
  if (n > COMENTARIO_MAX) return `El comentario admite hasta ${COMENTARIO_MAX} caracteres.`;
  return null;
}

/** Clasificación vigente que el oficial confirma o corrige. */
export const vigente = (r: Pick<ItemRespuesta, "estado_final" | "declarado">): Clasificacion | null =>
  r.estado_final ?? r.declarado;

export function decisionDe(r: Pick<ItemRespuesta, "estado_final" | "declarado">, elegida: Resolutiva | null): Decision | null {
  if (!elegida) return null;
  return elegida === vigente(r) ? "confirmada" : "corregida";
}

/** Texto del botón: dice exactamente qué pasa al pulsarlo. */
export function textoBotonDecision(r: Pick<ItemRespuesta, "estado_final" | "declarado">, elegida: Resolutiva | null): string {
  const d = decisionDe(r, elegida);
  if (!d || !elegida) return "Elige una clasificación";
  return d === "confirmada" ? `Confirmar «${NOMBRE_CLASIFICACION[elegida]}»` : `Corregir a «${NOMBRE_CLASIFICACION[elegida]}»`;
}

/** Clasificación sugerida al abrir: la vigente si es resolutiva; si no, la que propuso la IA. */
export function sugerida(r: Pick<ItemRespuesta, "estado_final" | "declarado" | "llm">): Resolutiva | null {
  const v = vigente(r);
  if (v && v !== "requiere_revision") return v;
  const ia = r.llm?.clasificacion;
  return ia && ia !== "requiere_revision" ? ia : null;
}

/**
 * Los tres pasos de la cadena de decisión: lo que declaró la organización, lo que propuso la
 * IA y lo que queda vigente. `quiebre` marca dónde la IA no coincidió con lo declarado.
 */
export function cadenaDecision(r: ItemRespuesta) {
  const ia = r.llm?.clasificacion ?? null;
  return {
    declarado: r.declarado,
    ia,
    confianza: r.llm?.confianza ?? null,
    vigente: vigente(r),
    fuente: r.fuente,
    quiebre: Boolean(ia && r.declarado && r.declarado !== "requiere_revision" && ia !== r.declarado),
  };
}

export const NOMBRE_FUENTE: Record<string, string> = {
  usuario: "lo declarado por la organización",
  llm: "la decisión de la IA",
  seguridad: "el bloqueo de seguridad",
  revision: "una revisión humana",
};

/** Siguiente elemento pendiente tras resolver uno (para no volver a la lista a cada rato). */
export function siguientePendiente<T extends { id: number; pendiente: boolean }>(items: T[], actual: number): T | null {
  const i = items.findIndex((x) => x.id === actual);
  const resto = [...items.slice(i + 1), ...items.slice(0, Math.max(i, 0))];
  return resto.find((x) => x.pendiente && x.id !== actual) ?? null;
}
