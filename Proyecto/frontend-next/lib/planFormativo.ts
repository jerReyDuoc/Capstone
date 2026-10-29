/**
 * HU-12 · Plan formativo: textos, filtros y exportación (lógica pura, probada en tests/).
 *
 * El plan lo arma el backend (app/application/informes/analisis.py → construir_plan):
 * mapea cada brecha a la ruta de su catálogo, asigna el nivel de cada dimensión según su
 * puntaje y ordena los módulos. Aquí solo se presenta.
 */
import { celdaCsv } from "./exportar";
import type { DimensionPlanApi, ModuloPlanApi, NivelFormativo, PlanFormativoApi, Severidad } from "./types";

export const NIVELES_FORMATIVOS: NivelFormativo[] = ["Inicial", "Intermedio", "Avanzado"];

/** Mismos cortes que analisis.nivel_por_puntaje (backend). */
export function nivelPorPuntaje(puntaje: number | null | undefined): NivelFormativo {
  const p = puntaje ?? 0;
  if (p <= 50) return "Inicial";
  if (p <= 75) return "Intermedio";
  return "Avanzado";
}

export const NIVEL_FORMATIVO_INFO: Record<NivelFormativo, { rango: string; enfoque: string }> = {
  Inicial: { rango: "0–50 pts", enfoque: "Bases: conocer las obligaciones y aplicar los controles mínimos." },
  Intermedio: { rango: "51–75 pts", enfoque: "Práctica: aplicar los controles con responsables, registros y evidencia." },
  Avanzado: { rango: "76–100 pts", enfoque: "Mejora continua: medir, auditar y resolver casos complejos." },
};

export const PRIORIDAD_TEXTO: Record<ModuloPlanApi["prioridad"], string> = {
  Crítica: "Urgente",
  Alta: "Prioritario",
  Media: "Planificar",
  Baja: "Cuando se pueda",
  "Sin clasificar": "Por clasificar",
  Complementario: "Base del nivel",
};

const PESO: Record<ModuloPlanApi["prioridad"], number> = {
  Crítica: 0, Alta: 1, Media: 2, Baja: 3, "Sin clasificar": 4, Complementario: 5,
};

export interface FiltrosPlan {
  nivel: NivelFormativo | null;
  /** Solo módulos que activó alguna brecha (oculta las rutas base del nivel). */
  soloBrechas: boolean;
}

export const FILTROS_PLAN_VACIOS: FiltrosPlan = { nivel: null, soloBrechas: false };

export function filtrarDimension(d: DimensionPlanApi, f: FiltrosPlan): ModuloPlanApi[] {
  return d.modulos.filter((m) => (!f.nivel || m.nivel === f.nivel) && (!f.soloBrechas || m.motivo === "brechas"));
}

/** La dimensión que conviene atender primero: la de módulo más urgente y, si empata, menor puntaje. */
export function dimensionPrioritaria(plan: PlanFormativoApi): DimensionPlanApi | null {
  const peso = (d: DimensionPlanApi) => Math.min(99, ...d.modulos.map((m) => PESO[m.prioridad]));
  return (
    [...plan.dimensiones]
      .filter((d) => d.modulos.some((m) => m.motivo === "brechas"))
      .sort((a, b) => peso(a) - peso(b) || (a.puntaje ?? 101) - (b.puntaje ?? 101))[0] ?? null
  );
}

export function contarSeveridades(m: ModuloPlanApi): Partial<Record<Severidad, number>> {
  const c: Partial<Record<Severidad, number>> = {};
  for (const b of m.brechas) c[b.severidad] = (c[b.severidad] ?? 0) + 1;
  return c;
}

/** CSV del plan (un módulo por fila) para cargarlo en el LMS o en una planilla de capacitación. */
export function planACsv(plan: PlanFormativoApi, separador = ";"): string {
  const titulos = [
    "Dimensión", "Nivel asignado a la dimensión", "Puntaje dimensión", "Módulo", "Nivel del módulo",
    "Prioridad", "Motivo", "Horas", "Modalidad", "Público objetivo", "Objetivo", "Objetivos específicos",
    "Brechas que cubre (prioridad)",
  ];
  const filas = plan.dimensiones.flatMap((d) =>
    d.modulos.map((m) => [
      d.dominio, d.nivel_asignado, d.puntaje, m.ruta.nombre, m.nivel, PRIORIDAD_TEXTO[m.prioridad],
      m.motivo === "brechas" ? "Activado por brechas" : "Base del nivel asignado", m.ruta.horas,
      m.ruta.modalidad, m.ruta.publico_objetivo, m.ruta.objetivo, m.ruta.objetivos_especificos.join(" | "),
      m.brechas.map((b) => `#${b.prioridad}`).join(", "),
    ]),
  );
  const lineas = [titulos, ...filas].map((f) => f.map((v) => celdaCsv(v as string | number | null)).join(separador));
  return `﻿${lineas.join("\r\n")}\r\n`;
}

export const horasTexto = (h: number | null | undefined) => (h == null ? "—" : `${h} h`);
