/**
 * HU-11 · Severidad de las brechas normativas.
 *
 * El catálogo del backend clasifica cada control con un IMPACTO (Alta / Media / Baja),
 * pero no distingue cuánto falla la empresa. La severidad cruza ambas cosas:
 *
 *                   │ No cumplido │ Parcialmente cumplido
 *   ────────────────┼─────────────┼──────────────────────
 *   Impacto Alto    │  CRÍTICA    │  Alta
 *   Impacto Medio   │  Alta       │  Media
 *   Impacto Bajo    │  Media      │  Baja
 *
 * - Si el catálogo ya dice "Crítica", se respeta tal cual.
 * - Sin impacto en el catálogo ni en el control → "Sin clasificar" (se muestra, no se esconde).
 *
 * Toda la regla vive aquí: si el PO cambia la matriz, se edita solo MATRIZ_SEVERIDAD.
 */
import { normalizarCriticidad } from "./madurez";
import type { Criticidad, EstadoBrecha, Severidad } from "./types";

export const SEVERIDADES: Severidad[] = ["Crítica", "Alta", "Media", "Baja", "Sin clasificar"];

/** Las cuatro del criterio de aceptación, en orden de atención. */
export const SEVERIDADES_PRINCIPALES: Exclude<Severidad, "Sin clasificar">[] = ["Crítica", "Alta", "Media", "Baja"];

export type ImpactoConocido = Exclude<Criticidad, "Sin clasificar">;

export const MATRIZ_SEVERIDAD: Record<ImpactoConocido, Record<EstadoBrecha, Severidad>> = {
  Alta: { no_cumplido: "Crítica", parcialmente_cumplido: "Alta" },
  Media: { no_cumplido: "Alta", parcialmente_cumplido: "Media" },
  Baja: { no_cumplido: "Media", parcialmente_cumplido: "Baja" },
};

export const PESO_SEVERIDAD: Record<Severidad, number> = {
  Crítica: 0,
  Alta: 1,
  Media: 2,
  Baja: 3,
  "Sin clasificar": 4,
};

export type TonoSeveridad = "critico" | "naranja" | "medio" | "bajo" | "info";

/** Clase CSS: tone-<tono> (insignias) y sev-<tono> (tarjetas, filas, barras). */
export const SEVERIDAD_TONO: Record<Severidad, TonoSeveridad> = {
  Crítica: "critico",
  Alta: "naranja",
  Media: "medio",
  Baja: "bajo",
  "Sin clasificar": "info",
};

/** Microcopy de cada nivel: qué hacer, no un plazo legal. */
export const SEVERIDAD_GUIA: Record<Severidad, string> = {
  Crítica: "Atender de inmediato",
  Alta: "Resolver en el corto plazo",
  Media: "Planificar este trimestre",
  Baja: "Mejora continua",
  "Sin clasificar": "Impacto aún sin clasificar",
};

const esCriticaExplicita = (valor: string | null | undefined) => {
  const v = (valor ?? "").trim().toLowerCase();
  return v.startsWith("crít") || v.startsWith("crit");
};

/**
 * @param impactoCatalogo criticidad cruda del catálogo de brechas (puede venir "ALTA", "crítica"…)
 * @param impactoControl  criticidad cruda del control, usada solo si el catálogo no trae
 */
export function calcularSeveridad(
  impactoCatalogo: string | null | undefined,
  estado: EstadoBrecha,
  impactoControl?: string | null,
): { severidad: Severidad; impacto: Criticidad } {
  const crudo = impactoCatalogo?.trim() ? impactoCatalogo : impactoControl;
  const impacto = normalizarCriticidad(crudo);
  if (esCriticaExplicita(crudo)) return { severidad: "Crítica", impacto };
  if (impacto === "Sin clasificar") return { severidad: "Sin clasificar", impacto };
  return { severidad: MATRIZ_SEVERIDAD[impacto][estado], impacto };
}

/** Concordancia para "Impacto alto/medio/bajo". */
export const IMPACTO_TEXTO: Record<ImpactoConocido, string> = { Alta: "alto", Media: "medio", Baja: "bajo" };

export function contarPorSeveridad(items: { severidad: Severidad }[]): Record<Severidad, number> {
  const base = Object.fromEntries(SEVERIDADES.map((s) => [s, 0])) as Record<Severidad, number>;
  for (const b of items) base[b.severidad] += 1;
  return base;
}

/** "Crítica" → "críticas", para frases como "3 críticas". */
export function pluralSeveridad(s: Severidad, n: number) {
  if (s === "Sin clasificar") return "sin clasificar";
  const base = s.toLowerCase();
  return n === 1 ? base : `${base}s`;
}
