/**
 * HU-11 · Filtros del listado de brechas (lógica pura).
 * Los usan la vista de brechas (URL), las vistas fijadas en el Diagnóstico y las exportaciones,
 * así lo que se ve, lo que se fija y lo que se exporta es exactamente lo mismo.
 */
import { SEVERIDADES } from "./severidad";
import type { BrechaVista, EstadoBrecha, Severidad } from "./types";

export interface FiltrosBrechas {
  severidades: Severidad[];
  dominio: string | null;
  estado: EstadoBrecha | null;
  /** Texto libre: código, descripción, acción o ruta formativa. */
  texto: string;
}

export const FILTROS_VACIOS: FiltrosBrechas = { severidades: [], dominio: null, estado: null, texto: "" };

const ESTADOS: EstadoBrecha[] = ["no_cumplido", "parcialmente_cumplido"];

const sinTildes = (s: string) =>
  s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

export function filtrarBrechas(brechas: BrechaVista[], f: FiltrosBrechas): BrechaVista[] {
  const q = sinTildes(f.texto.trim());
  // "#3" busca por prioridad (los chips de Capacitación enlazan así, sin códigos internos)
  const prioridad = /^#(\d+)$/.exec(q)?.[1];
  return brechas.filter(
    (b) =>
      (f.severidades.length === 0 || f.severidades.includes(b.severidad)) &&
      (!f.dominio || b.dominio === f.dominio) &&
      (!f.estado || b.estado === f.estado) &&
      (!q ||
        (prioridad ? b.prioridad === Number(prioridad)
          : sinTildes([b.descripcion, b.accion ?? "", b.rutaFormativa ?? "", b.dominio].join(" ")).includes(q))),
  );
}

export const hayFiltros = (f: FiltrosBrechas) =>
  f.severidades.length > 0 || Boolean(f.dominio) || Boolean(f.estado) || f.texto.trim() !== "";

/** URL → filtros. `severidad` admite varios valores separados por coma: ?severidad=Crítica,Alta */
export function filtrosDesdeParams(p: { get(k: string): string | null }): FiltrosBrechas {
  const sev = (p.get("severidad") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter((s): s is Severidad => (SEVERIDADES as string[]).includes(s));
  const estado = p.get("estado");
  return {
    severidades: SEVERIDADES.filter((s) => sev.includes(s)), // orden canónico, sin duplicados
    dominio: p.get("dominio") || null,
    estado: ESTADOS.includes(estado as EstadoBrecha) ? (estado as EstadoBrecha) : null,
    texto: p.get("q") ?? "",
  };
}

/** Filtros → pares clave/valor para la URL (vacíos se omiten). */
export function filtrosAParams(f: FiltrosBrechas): Record<string, string> {
  const out: Record<string, string> = {};
  if (f.severidades.length) out.severidad = f.severidades.join(",");
  if (f.dominio) out.dominio = f.dominio;
  if (f.estado) out.estado = f.estado;
  if (f.texto.trim()) out.q = f.texto.trim();
  return out;
}

const ETIQUETA_ESTADO: Record<EstadoBrecha, string> = {
  no_cumplido: "No cumplidas",
  parcialmente_cumplido: "Parciales",
};

/** Nombre legible de un conjunto de filtros: "Crítica + Alta · Protección de Datos · No cumplidas". */
export function describirFiltros(f: FiltrosBrechas): string {
  const partes: string[] = [];
  if (f.severidades.length) partes.push(f.severidades.join(" + "));
  if (f.dominio) partes.push(f.dominio);
  if (f.estado) partes.push(ETIQUETA_ESTADO[f.estado]);
  if (f.texto.trim()) partes.push(`búsqueda “${f.texto.trim()}”`);
  return partes.length ? partes.join(" · ") : "Todas las brechas";
}

export function mismosFiltros(a: FiltrosBrechas, b: FiltrosBrechas) {
  return JSON.stringify(filtrosAParams(a)) === JSON.stringify(filtrosAParams(b));
}
