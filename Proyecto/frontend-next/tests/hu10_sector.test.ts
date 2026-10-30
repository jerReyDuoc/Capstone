/**
 * HU-10 · Comparativa sectorial con k-anonimato (k < 5 => se oculta).
 * La supresión la hace el backend (tests/test_hu10_benchmark_sectorial.py); aquí se prueba
 * que el frontend no muestre nada del sector cuando la cohorte es insuficiente (aunque un
 * backend previo enviara datos), que la advertencia aparezca y que no revele cuántas empresas hay.
 */
import { describe, expect, it } from "vitest";
import { construirPanel, construirSector } from "@/lib/adaptadores";
import { panelDemo } from "@/lib/demo";
import {
  advertenciaDe,
  describirTira,
  enEscala,
  formatoPuntos,
  ordenarParaComparar,
  textoAviso,
  tonoPosicion,
} from "@/lib/sector";
import { autorizarRuta } from "@/lib/servidor/proxy";
import type { ComparativaApi, ResumenApi, SectorApi } from "@/lib/types";

const RESUMEN: ResumenApi = {
  evaluacion_id: 7,
  puntaje_general: 52,
  nivel_madurez_general: "gestionado",
  total_controles_evaluados: 20,
  dominios: [
    { dominio_id: 1, dominio: "Datos", puntaje: 40, nivel_madurez: "en_desarrollo", total_controles_evaluados: 10 },
    { dominio_id: 2, dominio: "Riesgos", puntaje: 64, nivel_madurez: "gestionado", total_controles_evaluados: 10 },
  ],
};

const sector = (extra: Partial<SectorApi> = {}): SectorApi => ({
  rubro_id: 1,
  rubro: "Retail",
  k_minimo: 5,
  cohorte_suficiente: true,
  empresas: 12,
  promedio: 58,
  mediana: 57,
  percentil_25: 45,
  percentil_75: 70,
  tu_puntaje: 52,
  diferencia: -6,
  posicion: "franja_central",
  dimensiones_publicadas: 2,
  dimensiones_suprimidas: 0,
  advertencia: null,
  ...extra,
});

const comparativa = (s: SectorApi, filas: Partial<ComparativaApi["comparativas"][number]>[] = []): ComparativaApi => ({
  evaluacion_id: 7,
  rubro_id: s.rubro_id,
  meta_puntaje: 75,
  k_minimo: 5,
  sector: s,
  comparativas: RESUMEN.dominios.map((d, i) => ({
    dominio: d.dominio,
    tu_puntaje: d.puntaje,
    tu_nivel: d.nivel_madurez,
    promedio_industria: 55,
    mediana_industria: null,
    percentil_25: null,
    percentil_75: null,
    cohorte_suficiente: true,
    empresas: 12,
    muestras: 12,
    posicion: "bajo_promedio",
    diferencia_vs_promedio: (d.puntaje ?? 0) - 55,
    meta: 75,
    ...filas[i],
  })),
});

const panel = (c: ComparativaApi | null) => construirPanel({ resumen: RESUMEN, comparativa: c, respuestas: [], catalogo: [] });

describe("C1 · promedio general y por dimensión del sector", () => {
  it("lleva el bloque sector al panel con la posición", () => {
    const p = panel(comparativa(sector()));
    expect(p.sector).toMatchObject({ rubro: "Retail", promedio: 58, p25: 45, p75: 70, posicion: "franja_central", empresas: 12 });
    expect(p.dominios.every((d) => d.cohorteSuficiente && d.promedioIndustria === 55)).toBe(true);
    expect(advertenciaDe(p.sector, p.sinRubro)).toBeNull();
  });

  it("sin bloque sector (backend previo) no inventa uno", () => {
    expect(construirSector(null, 50)).toBeNull();
    expect(panel(null).sector).toBeNull();
  });
});

describe("C2 · supresión con k < 5", () => {
  it("con cohorte insuficiente no usa ningún dato del sector aunque llegara", () => {
    // Un backend previo podría mandar valores: el frontend los descarta igual
    const s = sector({ cohorte_suficiente: false, empresas: 3, promedio: 58, percentil_25: 40, posicion: "sobre_promedio" });
    const p = panel(comparativa(s, RESUMEN.dominios.map(() => ({ cohorte_suficiente: false, muestras: 3, empresas: 3 }))));
    expect(p.sector).toMatchObject({ cohorteSuficiente: false, empresas: null, promedio: null, p25: null, p75: null, diferencia: null, posicion: null });
    expect(p.dominios.every((d) => d.promedioIndustria === null && d.diferencia === null && d.muestras === 0 && d.posicion === null)).toBe(true);
    expect(p.tieneBenchmark).toBe(false);
  });

  it("la tira describe el sector como oculto, con el umbral y sin el número de empresas", () => {
    const t = describirTira({ nombre: "Datos", puntaje: 40, promedio: null, p25: null, p75: null, k: 5 });
    expect(t).toBe("Datos: tu empresa 40 de 100; promedio del sector oculto, menos de 5 empresas.");
  });
});

describe("C3 · advertencia en la interfaz", () => {
  it("cohorte insuficiente: aviso de privacidad sin revelar cuántas empresas hay", () => {
    const s = sector({ cohorte_suficiente: false, empresas: null, promedio: null, advertencia: null });
    const p = panel(comparativa(s));
    const codigo = advertenciaDe(p.sector, p.sinRubro);
    expect(codigo).toBe("COHORTE_INSUFICIENTE");
    const t = textoAviso(codigo!, 5, p.sector);
    expect(t.tono).toBe("aviso");
    expect(t.cuerpo).toMatch("menos de 5 empresas");
    expect(t.cuerpo).not.toMatch(/\b[0-4]\b/); // ningún conteo de la cohorte
  });

  it("supresión parcial por dimensión", () => {
    const s = sector({ dimensiones_publicadas: 1, dimensiones_suprimidas: 1 });
    const t = textoAviso(advertenciaDe(construirSector(comparativa(s), 52), false)!, 5, construirSector(comparativa(s), 52));
    expect(t.titulo).toBe("Una dimensión sin comparación sectorial");
    expect(t.cuerpo).toMatch("En 1 dimensión de 2 hay menos de 5 empresas");
  });

  it("usa el código del backend cuando lo trae", () => {
    const s = sector({ rubro_id: null, rubro: null, advertencia: { codigo: "SIN_RUBRO", mensaje: "…" } });
    expect(advertenciaDe(construirSector(comparativa(s), 52), true)).toBe("SIN_RUBRO");
    expect(textoAviso("SIN_RUBRO", 5, null).tono).toBe("info");
  });
});

describe("Utilidades de la vista", () => {
  it("formatos, escala y tonos", () => {
    expect(formatoPuntos(-6)).toBe("−6 pts");
    expect(formatoPuntos(4.25)).toBe("+4,3 pts");
    expect(formatoPuntos(0)).toBe("Igual");
    expect(formatoPuntos(null)).toBe("—");
    expect([enEscala(-3), enEscala(50), enEscala(140)]).toEqual([0, 50, 100]);
    expect(tonoPosicion("bajo_cuartil_inferior")).toBe("alto");
    expect(tonoPosicion("franja_central")).toBe("medio");
    expect(tonoPosicion("sobre_promedio")).toBe("bajo");
  });

  it("ordena primero las dimensiones con comparación, de mayor a menor distancia bajo el sector", () => {
    const p = panel(comparativa(sector(), [{ cohorte_suficiente: false, promedio_industria: null, diferencia_vs_promedio: null }, {}]));
    expect(ordenarParaComparar(p.dominios).map((d) => d.nombre)).toEqual(["Riesgos", "Datos"]);
  });

  it("el modo demo trae una dimensión suprimida y la advertencia parcial", () => {
    const p = panelDemo(9101);
    expect(p.sector?.cohorteSuficiente).toBe(true);
    expect(p.dominios.filter((d) => !d.cohorteSuficiente)).toHaveLength(1);
    expect(advertenciaDe(p.sector, p.sinRubro)).toBe("COHORTE_PARCIAL");
  });

  it("el BFF del encuestado sigue permitiendo la comparativa de su evaluación", () => {
    expect(autorizarRuta("GET", ["evaluaciones", "7", "comparativa"], 7).ok).toBe(true);
  });
});
