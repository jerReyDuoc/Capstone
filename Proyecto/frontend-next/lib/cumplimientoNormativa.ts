/**
 * Mejoras 19-11 · Cumplimiento por normativa (Plan de acción → Brechas).
 *
 * Se calcula con los datos REALES de la evaluación, nada queda fijo en el código:
 *   - las respuestas de la evaluación (GET /evaluaciones/{id}/respuestas) con su estado final;
 *   - la matriz de controles (GET /controles): cada control trae su `framework_fuente`
 *     (la normativa de la que sale) y así cada respuesta queda asociada a una normativa.
 *
 * Fórmula (la misma regla del puntaje por dimensión del backend, generar_resumen.py):
 *
 *                     cumplidos × 1  +  parciales × 0,5
 *   % normativa = ─────────────────────────────────────────── × 100
 *                  cumplidos + parciales + no cumplidos + en revisión
 *
 *   - "No aplica" y las preguntas sin responder no entran al cálculo.
 *   - "En revisión por la IA" cuenta como 0 hasta que se resuelva (igual que el backend: inyectar
 *     texto nunca puede subir el puntaje).
 *   - El % general usa la misma fórmula sobre todas las respuestas evaluadas de la evaluación.
 *
 * Normativas: salen de la matriz. Si mañana el administrador publica controles de otra norma,
 * aparece sola. Las que la matriz no tiene (hoy ISO/IEC 27001 e ISO/IEC 23894) no se inventan.
 */
import type { BrechaVista, ControlApi, RespuestaApi } from "./types";

export const PESO_CUMPLIDO = 1;
export const PESO_PARCIAL = 0.5;

export interface NormativaDef {
  /** Identificador estable para la URL (?normativa=ley-21719). */
  id: string;
  /** Nombre corto para las pestañas. */
  nombre: string;
  /** Nombre completo (tooltip y lectores de pantalla). */
  nombreCompleto: string;
}

/** Normativas conocidas, en el orden en que se muestran. El texto viene de `framework_fuente`. */
const CONOCIDAS: (NormativaDef & { patron: RegExp })[] = [
  { id: "ley-21719", nombre: "Ley 21.719", nombreCompleto: "Ley N.º 21.719 de protección de datos personales", patron: /21[.\s]?719/ },
  { id: "iso-27001", nombre: "ISO/IEC 27001", nombreCompleto: "ISO/IEC 27001 · Seguridad de la información", patron: /27001/ },
  { id: "iso-42001", nombre: "ISO/IEC 42001", nombreCompleto: "ISO/IEC 42001 · Sistema de gestión de IA", patron: /42001/ },
  { id: "nist-ai-rmf", nombre: "NIST AI RMF", nombreCompleto: "NIST AI RMF 100-1 · Marco de gestión de riesgos de IA", patron: /nist.*(rmf|100-1)/i },
  { id: "iso-23894", nombre: "ISO/IEC 23894", nombreCompleto: "ISO/IEC 23894 · Gestión de riesgos de IA", patron: /23894/ },
  { id: "nist-ai-600", nombre: "NIST AI 600-1", nombreCompleto: "NIST AI 600-1 · Perfil de IA generativa", patron: /600-1/ },
  { id: "owasp-llm", nombre: "OWASP LLM", nombreCompleto: "OWASP Top 10 para aplicaciones con LLM", patron: /owasp/i },
];

const slugNormativa = (texto: string) =>
  texto
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

/** Traduce el `framework_fuente` de la matriz a una normativa (null si el control no la informa). */
export function normativaDe(framework: string | null | undefined): NormativaDef | null {
  const t = (framework ?? "").trim();
  if (!t) return null;
  const conocida = CONOCIDAS.find((c) => c.patron.test(t));
  if (conocida) return { id: conocida.id, nombre: conocida.nombre, nombreCompleto: conocida.nombreCompleto };
  return { id: slugNormativa(t), nombre: t, nombreCompleto: t };
}

const orden = (id: string) => {
  const i = CONOCIDAS.findIndex((c) => c.id === id);
  return i === -1 ? CONOCIDAS.length : i;
};

export interface ConteoCumplimiento {
  cumplidos: number;
  parciales: number;
  noCumplidos: number;
  enRevision: number;
  noAplica: number;
  /** Respuestas que entran al denominador (todo menos "no aplica" y sin responder). */
  evaluados: number;
  /** 0-100 con un decimal; null si no hay nada evaluado. */
  porcentaje: number | null;
}

export interface CumplimientoNormativa extends NormativaDef, ConteoCumplimiento {}

export interface CumplimientoVista {
  general: ConteoCumplimiento;
  normativas: CumplimientoNormativa[];
  /** id de control → id de normativa (para filtrar las brechas). */
  normativaPorControl: Record<number, string>;
}

function vacio(): ConteoCumplimiento {
  return { cumplidos: 0, parciales: 0, noCumplidos: 0, enRevision: 0, noAplica: 0, evaluados: 0, porcentaje: null };
}

function sumar(c: ConteoCumplimiento, estado: string | null) {
  switch (estado) {
    case "cumplido": c.cumplidos++; break;
    case "parcialmente_cumplido": c.parciales++; break;
    case "no_cumplido": c.noCumplidos++; break;
    case "requiere_revision": c.enRevision++; break;
    case "no_aplica": c.noAplica++; break;
    default: return; // sin responder: no cuenta
  }
}

/** Aplica la fórmula a un conteo ya sumado. */
export function porcentajeCumplimiento(c: Pick<ConteoCumplimiento, "cumplidos" | "parciales" | "noCumplidos" | "enRevision">): number | null {
  const evaluados = c.cumplidos + c.parciales + c.noCumplidos + c.enRevision;
  if (evaluados === 0) return null;
  return Math.round(((c.cumplidos * PESO_CUMPLIDO + c.parciales * PESO_PARCIAL) / evaluados) * 1000) / 10;
}

function cerrar(c: ConteoCumplimiento): ConteoCumplimiento {
  c.evaluados = c.cumplidos + c.parciales + c.noCumplidos + c.enRevision;
  c.porcentaje = porcentajeCumplimiento(c);
  return c;
}

export function calcularCumplimiento(respuestas: RespuestaApi[], controles: ControlApi[]): CumplimientoVista {
  const normativaPorControl: Record<number, string> = {};
  const defs = new Map<string, NormativaDef>();
  for (const c of controles) {
    const n = normativaDe(c.framework_fuente);
    if (!n) continue;
    normativaPorControl[c.id_control] = n.id;
    defs.set(n.id, n);
  }

  const general = vacio();
  const porNormativa = new Map<string, ConteoCumplimiento>();
  for (const r of respuestas) {
    const estado = r.estado_clasificacion_final ?? r.estado_clasificacion; // el final manda (como estadoEfectivo)
    sumar(general, estado);
    const id = r.matriz_controles_id_control != null ? normativaPorControl[r.matriz_controles_id_control] : undefined;
    if (!id) continue;
    const c = porNormativa.get(id) ?? vacio();
    sumar(c, estado);
    porNormativa.set(id, c);
  }

  const normativas = [...porNormativa.entries()]
    .map(([id, c]) => ({ ...defs.get(id)!, ...cerrar(c) }))
    // Una normativa con todo "no aplica" no aporta nada que mostrar
    .filter((n) => n.evaluados > 0)
    .sort((a, b) => orden(a.id) - orden(b.id) || a.nombre.localeCompare(b.nombre, "es"));

  return { general: cerrar(general), normativas, normativaPorControl };
}

/* ------------------------------------------------------------ brechas por tipo */

export interface BrechasPorTipo {
  cumple: number;
  parcial: number;
  noCumple: number;
  critico: number;
}

/**
 * Tarjeta "Brechas por tipo". Los grupos no se repiten: una brecha de severidad crítica se cuenta
 * solo en "Crítico" (no también en "No cumple" o "Parcial"). "Cumple" son los controles cumplidos.
 */
export function brechasPorTipo(cumplidos: number, brechas: Pick<BrechaVista, "estado" | "severidad">[]): BrechasPorTipo {
  const t: BrechasPorTipo = { cumple: cumplidos, parcial: 0, noCumple: 0, critico: 0 };
  for (const b of brechas) {
    if (b.severidad === "Crítica") t.critico++;
    else if (b.estado === "no_cumplido") t.noCumple++;
    else t.parcial++;
  }
  return t;
}

/** Brechas de una normativa (null = todas). */
export function filtrarPorNormativa<T extends Pick<BrechaVista, "controlId">>(
  brechas: T[],
  normativa: string | null,
  normativaPorControl: Record<number, string>,
): T[] {
  if (!normativa) return brechas;
  return brechas.filter((b) => b.controlId != null && normativaPorControl[b.controlId] === normativa);
}

/* ------------------------------------------------------------ responsable sugerido */

/**
 * Quién suele hacerse cargo de cerrar la brecha, según su dimensión. Es una SUGERENCIA (la
 * plataforma no guarda responsables por brecha); usa el mismo vocabulario que el Agente IA Tutor
 * (app/application/ai/schemas/tutor.py · ResponsableSugerido).
 */
const RESPONSABLE_POR_DOMINIO: Record<string, string> = {
  "Protección de Datos": "Encargado de Datos",
  "Gobernanza de IA": "Alta dirección / Directorio",
  "Gestión de Riesgos": "Gestión de Riesgos",
  "Uso Responsable": "Seguridad de la información",
};

export function responsableSugerido(dominio: string): string {
  return RESPONSABLE_POR_DOMINIO[dominio] ?? "Oficial de Cumplimiento";
}

/** Texto del porcentaje: "62,5 %" (o "—" si no hay datos). */
export function formatoPorcentaje(p: number | null): string {
  if (p == null) return "—";
  return `${p.toLocaleString("es-CL", { maximumFractionDigits: 1 })} %`;
}
