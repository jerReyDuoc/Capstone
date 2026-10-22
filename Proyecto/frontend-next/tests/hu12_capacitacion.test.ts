/**
 * HU-12 · Plan formativo en el panel + meta de cumplimiento + informe PDF/correo por el BFF.
 * El plan lo calcula el backend (tests/test_hu12_plan_formativo.py); aquí se prueba lo que
 * el frontend hace con él.
 */
import { describe, expect, it } from "vitest";
import { construirPanel, notaIndustria } from "@/lib/adaptadores";
import { nombreDesdeDisposicion } from "@/lib/api";
import { planDemo } from "@/lib/demo";
import { formatoDiferenciaMeta, META_POR_DEFECTO } from "@/lib/madurez";
import {
  dimensionPrioritaria,
  filtrarDimension,
  nivelPorPuntaje,
  planACsv,
  PRIORIDAD_TEXTO,
} from "@/lib/planFormativo";
import { autorizarRuta, filtrarQuery } from "@/lib/servidor/proxy";
import type { ComparativaApi, PlanFormativoApi, ResumenApi } from "@/lib/types";

const RESUMEN: ResumenApi = {
  evaluacion_id: 7,
  puntaje_general: 55,
  nivel_madurez_general: "gestionado",
  total_controles_evaluados: 20,
  dominios: [
    { dominio_id: 1, dominio: "Protección de Datos", puntaje: 40, nivel_madurez: "en_desarrollo", total_controles_evaluados: 10 },
    { dominio_id: 2, dominio: "Gobernanza de IA", puntaje: 80, nivel_madurez: "optimizado", total_controles_evaluados: 10 },
  ],
};

const comparativa = (extra: Partial<ComparativaApi> = {}, suficiente = true): ComparativaApi => ({
  evaluacion_id: 7,
  rubro_id: 3,
  meta_puntaje: 70,
  muestras_minimas: 3,
  comparativas: RESUMEN.dominios.map((d) => ({
    dominio: d.dominio,
    tu_puntaje: d.puntaje,
    tu_nivel: d.nivel_madurez,
    promedio_industria: 60,
    mediana_industria: 60,
    maximo_industria: 90,
    minimo_industria: 10,
    muestras: suficiente ? 5 : 1,
    referencia_suficiente: suficiente,
    diferencia_vs_promedio: (d.puntaje ?? 0) - 60,
    meta: 70,
    diferencia_vs_meta: (d.puntaje ?? 0) - 70,
    cumple_meta: (d.puntaje ?? 0) >= 70,
  })),
  ...extra,
});

const panel = (c: ComparativaApi | null) => construirPanel({ resumen: RESUMEN, comparativa: c, respuestas: [], catalogo: [] });

describe("Comparativa al completar: meta siempre, rubro solo con muestras suficientes", () => {
  it("usa la meta del backend y calcula cuánto falta por dimensión", () => {
    const p = panel(comparativa());
    expect(p.meta).toBe(70);
    expect(p.dominios.map((d) => [d.nombre, d.meta, d.diferenciaMeta])).toEqual([
      ["Gobernanza de IA", 70, 10],
      ["Protección de Datos", 70, -30],
    ]);
    expect(p.tieneBenchmark).toBe(true);
    expect(notaIndustria(p)).toBeNull();
  });

  it("sin comparativa (backend antiguo o caída) igual muestra la meta por defecto", () => {
    const p = panel(null);
    expect(p.meta).toBe(META_POR_DEFECTO);
    expect(p.dominios.every((d) => d.meta === META_POR_DEFECTO)).toBe(true);
    expect(p.tieneBenchmark).toBe(false);
    expect(notaIndustria(p)).toMatch("no tiene rubro");
  });

  it("con pocas evaluaciones del rubro no muestra un promedio engañoso y explica por qué", () => {
    const p = panel(comparativa({}, false));
    expect(p.dominios.every((d) => d.promedioIndustria === null && d.diferencia === null)).toBe(true);
    expect(notaIndustria(p)).toBe("El promedio del rubro aparece con al menos 3 evaluaciones completadas (hoy hay 1, la tuya).");
  });

  it("textos de la distancia a la meta", () => {
    expect(formatoDiferenciaMeta(-12.5)).toBe("Faltan 12,5 pts para la meta");
    expect(formatoDiferenciaMeta(4)).toBe("Cumple la meta (+4)");
    expect(formatoDiferenciaMeta(0)).toBe("Justo en la meta");
  });
});

const PLAN: PlanFormativoApi = {
  evaluacion_id: 7,
  resumen: { dimensiones: 2, modulos: 3, horas: 16, brechas_total: 3, brechas_mapeadas: 2, cobertura_mapeo: 66.7 },
  brechas_sin_ruta: [{ codigo: "ERR-X", control_codigo: null, dominio: "Gobernanza de IA", severidad: "Baja", estado: "parcialmente_cumplido", prioridad: 3 }],
  dimensiones: [
    {
      dominio_id: 2, dominio: "Gobernanza de IA", puntaje: 80, nivel_madurez: "optimizado", nivel_asignado: "Avanzado",
      objetivo_nivel: "Mejora continua", brechas: 1, horas: 10,
      modulos: [{
        nivel: "Avanzado", motivo: "nivel", prioridad: "Complementario", brechas: [],
        ruta: { id: 6, nombre: "Gobernanza de IA - Avanzado", dominio: "Gobernanza de IA", nivel: "Avanzado", objetivo: "Dirigir", objetivos_especificos: ["a"], contenidos: [], horas: 10, modalidad: "Taller", publico_objetivo: "Directorio" },
      }],
    },
    {
      dominio_id: 1, dominio: "Protección de Datos", puntaje: 40, nivel_madurez: "en_desarrollo", nivel_asignado: "Inicial",
      objetivo_nivel: "Bases", brechas: 2, horas: 6,
      modulos: [
        {
          nivel: "Inicial", motivo: "brechas", prioridad: "Crítica",
          brechas: [{ codigo: "ERR-DAT-001", control_codigo: "DAT-001", dominio: "Protección de Datos", severidad: "Crítica", estado: "no_cumplido", prioridad: 1 }],
          ruta: { id: 1, nombre: "Protección de Datos - Inicial", dominio: "Protección de Datos", nivel: "Inicial", objetivo: "=Conocer", objetivos_especificos: ["x", "y"], contenidos: ["c"], horas: 4, modalidad: null, publico_objetivo: null },
        },
        {
          nivel: "Intermedio", motivo: "brechas", prioridad: "Media",
          brechas: [{ codigo: "DAT-002", control_codigo: "DAT-002", dominio: "Protección de Datos", severidad: "Media", estado: "parcialmente_cumplido", prioridad: 2 }],
          ruta: { id: 2, nombre: "Protección de Datos - Intermedio", dominio: "Protección de Datos", nivel: "Intermedio", objetivo: null, objetivos_especificos: [], contenidos: [], horas: 2, modalidad: null, publico_objetivo: null },
        },
      ],
    },
  ],
};

describe("HU-12 · Plan formativo en el panel", () => {
  it("C2 · niveles con los mismos cortes que el backend", () => {
    expect([0, 50, 50.5, 75, 76, null].map((p) => nivelPorPuntaje(p))).toEqual(
      ["Inicial", "Inicial", "Intermedio", "Intermedio", "Avanzado", "Inicial"],
    );
  });

  it("C3 · filtros por nivel y solo módulos que cierran brechas", () => {
    const datos = PLAN.dimensiones[1];
    expect(filtrarDimension(datos, { nivel: "Inicial", soloBrechas: false }).map((m) => m.ruta.id)).toEqual([1]);
    expect(filtrarDimension(PLAN.dimensiones[0], { nivel: null, soloBrechas: true })).toHaveLength(0);
    expect(PRIORIDAD_TEXTO.Complementario).toBe("Base del nivel");
  });

  it("'Empieza por' elige la dimensión con el módulo más urgente", () => {
    expect(dimensionPrioritaria(PLAN)?.dominio).toBe("Protección de Datos");
    expect(dimensionPrioritaria({ ...PLAN, dimensiones: [PLAN.dimensiones[0]] })).toBeNull();
  });

  it("CSV del plan: una fila por módulo, BOM y celdas seguras contra fórmulas", () => {
    const csv = planACsv(PLAN);
    const lineas = csv.trim().split("\r\n");
    expect(csv.startsWith("﻿")).toBe(true);
    expect(lineas).toHaveLength(1 + 3);
    expect(lineas[2]).toContain('"Activado por brechas"');
    expect(lineas[2]).toContain(`"'=Conocer"`); // inyección CSV neutralizada
    expect(lineas[2]).toContain('"ERR-DAT-001"');
  });

  it("modo demo: el plan sigue la misma regla (mapeo + ruta base del nivel)", () => {
    const plan = planDemo(9101);
    expect(plan.resumen.brechas_mapeadas + plan.brechas_sin_ruta.length).toBe(plan.resumen.brechas_total);
    for (const d of plan.dimensiones) {
      expect(d.nivel_asignado).toBe(nivelPorPuntaje(d.puntaje));
      expect(d.modulos.some((m) => m.ruta.nivel === d.nivel_asignado), d.dominio).toBe(true);
    }
    expect(plan.resumen.modulos).toBe(plan.dimensiones.reduce((s, d) => s + d.modulos.length, 0));
  });
});

describe("BFF · plan, PDF y correo solo para la evaluación de la sesión", () => {
  it("permite las rutas nuevas y marca el PDF como binario y el correo con IP", () => {
    expect(autorizarRuta("GET", ["evaluaciones", "12", "plan-formativo"], 12).ok).toBe(true);
    expect(autorizarRuta("GET", ["evaluaciones", "12", "informe", "pdf"], 12)).toMatchObject({ ok: true, binario: true, conIp: false });
    expect(autorizarRuta("POST", ["evaluaciones", "12", "informe", "enviar"], 12)).toMatchObject({ ok: true, conIp: true, binario: false });
  });

  it("bloquea otras evaluaciones, métodos y trucos", () => {
    for (const [m, seg] of [
      ["GET", ["evaluaciones", "13", "plan-formativo"]],
      ["GET", ["evaluaciones", "13", "informe", "pdf"]],
      ["POST", ["evaluaciones", "13", "informe", "enviar"]],
      ["GET", ["evaluaciones", "12", "informe", "enviar"]],
      ["POST", ["evaluaciones", "12", "informe", "pdf"]],
      ["GET", ["evaluaciones", "12", "informe.pdf"]],
    ] as const) {
      expect(autorizarRuta(m, [...seg], 12).ok, `${m} ${seg.join("/")}`).toBe(false);
    }
  });

  it("deja pasar los filtros del PDF y nada más", () => {
    const q = filtrarQuery(new URLSearchParams("severidad=Crítica,Alta&dominio=Protección de Datos&estado=no_cumplido&q=ERR&token=x"));
    expect(new URLSearchParams(q.slice(1)).get("severidad")).toBe("Crítica,Alta");
    expect(q).not.toContain("token");
    expect(filtrarQuery(new URLSearchParams(`q=${"x".repeat(81)}`))).toBe("");
  });

  it("solo acepta nombres de archivo PDF simples desde Content-Disposition", () => {
    expect(nombreDesdeDisposicion('attachment; filename="informe_evaluacion-7_2026-10-22.pdf"', "x.pdf")).toBe("informe_evaluacion-7_2026-10-22.pdf");
    expect(nombreDesdeDisposicion('attachment; filename="../../etc.sh"', "respaldo.pdf")).toBe("respaldo.pdf");
    expect(nombreDesdeDisposicion(null, "respaldo.pdf")).toBe("respaldo.pdf");
  });
});
