/**
 * HU-21 · Página "Informe" (vista previa de la portada, ficha y descarga).
 * El PDF y la ficha los arma el backend (tests/test_hu21_informe_pdf.py); aquí se prueba
 * lo que el frontend hace con ellos y que el BFF deje pasar la ficha.
 */
import { describe, expect, it } from "vitest";
import { panelDemo } from "@/lib/demo";
import {
  anchoBarra,
  codigoValido,
  digitoVerificador,
  fechaEvaluacion,
  fichaDemo,
  formatoFechaInforme,
  formatoPuntajeInforme,
  textoSeveridades,
} from "@/lib/informe";
import { autorizarRuta } from "@/lib/servidor/proxy";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";

describe("código de evaluación (igual al backend)", () => {
  it("dígito verificador módulo 11 como el RUT", () => {
    expect(digitoVerificador(11111111)).toBe("1");
    expect(digitoVerificador(12345678)).toBe("5");
    expect(digitoVerificador(6)).toBe("K");
    expect(digitoVerificador(0)).toBe("0");
    expect(digitoVerificador(123)).toBe("6"); // CIA-2026-000123-6 en las pruebas del backend
  });

  it("valida el formato y detecta un código mal transcrito", () => {
    expect(codigoValido("CIA-2026-000123-6")).toBe(true);
    expect(codigoValido("cia-2026-000123-6")).toBe(true);
    expect(codigoValido("CIA-2026-000123-7")).toBe(false);
    expect(codigoValido("CIA-2026-000132-6")).toBe(false);
    expect(codigoValido("CIA-26-000123-6")).toBe(false);
    expect(codigoValido("")).toBe(false);
  });
});

describe("formatos de la ficha", () => {
  it("fechas en hora de Chile; un día sin hora no se corre por la zona", () => {
    expect(formatoFechaInforme("2026-10-30")).toMatch(/30.+octubre.+2026/);
    // 02:30 UTC del 3 de noviembre = 23:30 del 2 de noviembre en Chile (UTC-3)
    expect(formatoFechaInforme("2026-11-03T02:30:00", true)).toMatch(/02.+noviembre.+2026/);
    expect(formatoFechaInforme(null)).toBe("Sin fecha");
    expect(formatoFechaInforme("no-es-fecha")).toBe("Sin fecha");
  });

  it("la fecha de la evaluación es la de cierre y, si no hay, la de inicio", () => {
    expect(fechaEvaluacion({ fecha_completado: "2026-11-02T15:30:00", fecha_evaluacion: "2026-10-30" })).toMatch(/noviembre/);
    expect(fechaEvaluacion({ fecha_completado: null, fecha_evaluacion: "2026-10-30" })).toMatch(/octubre/);
  });

  it("resumen de severidades en lenguaje natural", () => {
    expect(textoSeveridades({ "Crítica": 1, Alta: 2, Media: 1 })).toBe("1 crítica, 2 altas y 1 media");
    expect(textoSeveridades({ Baja: 3 })).toBe("3 bajas");
    expect(textoSeveridades({})).toBe("");
  });

  it("puntajes con coma decimal y barras acotadas", () => {
    expect(formatoPuntajeInforme(55.5)).toBe("55,5");
    expect(formatoPuntajeInforme(80)).toBe("80");
    expect(formatoPuntajeInforme(null)).toBe("—");
    expect(anchoBarra(120)).toBe(100);
    expect(anchoBarra(-4)).toBe(0);
    expect(anchoBarra(null)).toBe(0);
  });
});

describe("modo demo", () => {
  it("la ficha de ejemplo trae siempre los 5 puntajes y un código válido", () => {
    const f = fichaDemo(panelDemo(42));
    expect(f.puntajes).toHaveLength(5);
    expect(f.puntajes[0].global).toBe(true);
    expect(f.puntajes.map((p) => p.nombre).slice(1)).toEqual([
      "Gobernanza de IA", "Gestión de Riesgos", "Protección de Datos", "Uso Responsable",
    ]);
    expect(codigoValido(f.codigo)).toBe(true);
  });
});

describe("BFF: la ficha pasa solo para la evaluación de la sesión", () => {
  it("encuestado (/bff/api)", () => {
    expect(autorizarRuta("GET", ["evaluaciones", "7", "informe", "ficha"], 7).ok).toBe(true);
    expect(autorizarRuta("GET", ["evaluaciones", "8", "informe", "ficha"], 7).ok).toBe(false);
    expect(autorizarRuta("POST", ["evaluaciones", "7", "informe", "ficha"], 7).ok).toBe(false);
  });

  it("usuario definitivo (/bff/cliente/api)", () => {
    expect(autorizarRutaCliente("GET", ["evaluaciones", "7", "informe", "ficha"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["evaluaciones", "7", "informe", "ficha"]).ok).toBe(false);
  });
});
