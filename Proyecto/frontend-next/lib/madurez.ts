import type { Criticidad, NivelMadurez } from "./types";

/**
 * Mismos cortes que el backend (generate_resumen.nivel_madurez):
 * <=25 inicial · <=50 en desarrollo · <=75 gestionado · >75 optimizado.
 */
export function nivelDesdePuntaje(puntaje: number): NivelMadurez {
  if (puntaje <= 25) return "inicial";
  if (puntaje <= 50) return "en_desarrollo";
  if (puntaje <= 75) return "gestionado";
  return "optimizado";
}

export const NIVELES: Record<
  NivelMadurez,
  { etiqueta: string; descripcion: string; tono: "alto" | "medio" | "bajo" | "ok" }
> = {
  inicial: {
    etiqueta: "Inicial",
    descripcion: "Prácticas ad hoc, sin controles formales de gobernanza.",
    tono: "alto",
  },
  en_desarrollo: {
    etiqueta: "En desarrollo",
    descripcion: "Existen controles, pero no se aplican de forma consistente.",
    tono: "medio",
  },
  gestionado: {
    etiqueta: "Gestionado",
    descripcion: "Controles definidos, documentados y con responsables.",
    tono: "bajo",
  },
  optimizado: {
    etiqueta: "Optimizado",
    descripcion: "Mejora continua medida y revisada periódicamente.",
    tono: "ok",
  },
};

export const CRITICIDADES: Criticidad[] = ["Alta", "Media", "Baja", "Sin clasificar"];

export const CRITICIDAD_TONO: Record<Criticidad, "alto" | "medio" | "bajo" | "info"> = {
  Alta: "alto",
  Media: "medio",
  Baja: "bajo",
  "Sin clasificar": "info",
};

/** El catálogo trae "Alta", "alta", "ALTA", "Crítica"… lo dejamos en 4 valores. */
export function normalizarCriticidad(valor: string | null | undefined): Criticidad {
  const v = (valor ?? "").trim().toLowerCase();
  if (v.startsWith("alt") || v.startsWith("crít") || v.startsWith("crit")) return "Alta";
  if (v.startsWith("med")) return "Media";
  if (v.startsWith("baj")) return "Baja";
  return "Sin clasificar";
}

export const formatoPuntaje = (n: number | null | undefined) =>
  n == null || Number.isNaN(n) ? "—" : new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1 }).format(n);

export function formatoDiferencia(n: number | null): string {
  if (n == null) return "Sin referencia";
  if (n === 0) return "Igual al promedio";
  const abs = formatoPuntaje(Math.abs(n));
  return n > 0 ? `+${abs} pts sobre el promedio` : `−${abs} pts bajo el promedio`;
}

/** Meta por defecto si el backend no la envía (igual a META_CUMPLIMIENTO_PUNTAJE). */
export const META_POR_DEFECTO = 75;

/** "Cumple la meta (+4)" · "Faltan 12 pts para la meta". */
export function formatoDiferenciaMeta(n: number): string {
  if (n >= 0) return n === 0 ? "Justo en la meta" : `Cumple la meta (+${formatoPuntaje(n)})`;
  return `Faltan ${formatoPuntaje(Math.abs(n))} pts para la meta`;
}
