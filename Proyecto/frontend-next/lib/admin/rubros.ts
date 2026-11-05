/**
 * Correcciones 05-11 · Rubros del panel interno (GET/POST/PATCH /api/admin/rubros).
 * El backend valida y normaliza; aquí solo lo obvio antes de enviar.
 */
import { pedir } from "@/lib/encuesta/cliente";

export interface RubroAdmin {
  id: number;
  nombre: string;
  /** Evaluaciones del autodiagnóstico hechas con este rubro. */
  evaluaciones: number;
  /** Empresas cliente de este rubro. */
  empresas: number;
}

const BASE = "/bff/admin/api/admin/rubros";

export const apiRubros = {
  listar: () => pedir<{ items: RubroAdmin[] }>(BASE),
  crear: (nombre: string) => pedir<RubroAdmin>(BASE, { method: "POST", json: { nombre } }),
  renombrar: (id: number, nombre: string) =>
    pedir<{ id: number; nombre: string }>(`${BASE}/${id}`, { method: "PATCH", json: { nombre } }),
};

export const RUBRO_MIN = 2;
export const RUBRO_MAX = 50;

export const normalizarRubro = (t: string) => t.replace(/\s+/g, " ").trim();

/** Error para mostrar junto al campo, o null si se puede enviar. */
export function errorRubro(nombre: string, existentes: Pick<RubroAdmin, "id" | "nombre">[], excepto?: number): string | null {
  const n = normalizarRubro(nombre);
  if (n.length < RUBRO_MIN || !/\p{L}/u.test(n)) return `Escribe un nombre de al menos ${RUBRO_MIN} letras.`;
  if (n.length > RUBRO_MAX) return `El nombre admite hasta ${RUBRO_MAX} caracteres.`;
  if (existentes.some((r) => r.id !== excepto && r.nombre.trim().toLocaleLowerCase("es") === n.toLocaleLowerCase("es"))) {
    return `Ya existe el rubro «${n}».`;
  }
  return null;
}

/** Correcciones 05-11: notas de versión que puso el sistema al sembrar la matriz; no se muestran. */
export function notaVisible(nota: string | null | undefined): string | null {
  if (!nota) return null;
  return /sembrada por las migraciones|registrada desde las tablas del cat[aá]logo/i.test(nota) ? null : nota;
}
