/**
 * HU-24 · Lógica pura del mantenedor de la matriz normativa y lista blanca del proxy.
 */
import { describe, expect, it } from "vitest";
import {
  aplicables,
  controlesPorDimension,
  datosDelFormulario,
  erroresFormulario,
  estadosDe,
  frasesCambios,
  ruta,
  valoresIniciales,
  type Contenido,
  type Control,
} from "@/lib/admin/matriz";
import { autorizarRutaAdmin } from "@/lib/servidor/proxyAdmin";

const control = (id: number, codigo: string, extra: Partial<Control> = {}): Control => ({
  id, codigo_control: codigo, framework_fuente: null, articulo_referencia: null, tipo_fuente: null, obligacion: null,
  pregunta_evaluacion: `¿${codigo}?`, aplicabilidad: null, evidencia_esperada: null, criticidad: "Alta",
  recomendacion: null, test_asociado: null, dominio_id: codigo.startsWith("DAT") ? 1 : 2, brecha_id: 1,
  aplica_siempre: false, filtros: [], activo: true, ...extra,
});

const contenido: Contenido = {
  esquema: 1,
  dominios: [{ id: 1, nombre_dominio: "Protección de Datos" }, { id: 2, nombre_dominio: "Gobernanza de IA" }],
  rutas: [],
  brechas: [],
  controles: [
    control(1, "DAT-001", { aplica_siempre: true }),
    control(2, "DAT-002", { filtros: [2] }),
    control(3, "GOB-001", { aplica_siempre: true }),
    control(4, "GOB-002", { filtros: [2, 3] }),
    control(5, "GOB-003", { aplica_siempre: true, activo: false }),
  ],
  preguntas_filtro: [
    { id: 1, codigo: "F1", orden: 1, pregunta: "¿Usa IA?", descripcion: null, activa: true, es_compuerta: true },
    { id: 2, codigo: "F2", orden: 2, pregunta: "¿Datos sensibles?", descripcion: null, activa: true, es_compuerta: false },
    { id: 3, codigo: "F3", orden: 3, pregunta: "¿Terceros?", descripcion: null, activa: false, es_compuerta: false },
  ],
};

describe("árbol de aplicabilidad (espejo del backend)", () => {
  it("la compuerta en NO deja el cuestionario vacío", () => {
    expect(aplicables(contenido, { F1: false, F2: true })).toEqual([]);
  });
  it("base + filtros en SÍ, sin retirados ni filtros retirados", () => {
    expect(aplicables(contenido, { F1: true })).toEqual(["DAT-001", "GOB-001"]);
    expect(aplicables(contenido, { F1: true, F2: true })).toEqual(["DAT-001", "DAT-002", "GOB-001", "GOB-002"]);
    expect(aplicables(contenido, { F1: true, F3: true })).toEqual(["DAT-001", "GOB-001"]); // F3 retirada
  });
  it("agrupa los controles activos por dimensión", () => {
    const g = controlesPorDimension(contenido);
    expect(g.map((x) => x.controles.map((c) => c.codigo_control))).toEqual([["DAT-001", "DAT-002"], ["GOB-001", "GOB-002"]]);
  });
});

describe("formulario de edición", () => {
  it("al editar envía solo lo que cambió y nunca el código de un elemento publicado", () => {
    const original = contenido.controles[0];
    const valores = { ...valoresIniciales("controles", original), codigo_control: "DAT-999", criticidad: "Media" };
    expect(datosDelFormulario("controles", valores, original)).toEqual({ criticidad: "Media" });
  });
  it("al crear envía el código y omite lo vacío; convierte números", () => {
    const valores = { ...valoresIniciales("controles"), codigo_control: "GOB-011", pregunta_evaluacion: "¿Algo?",
      dominio_id: "2", criticidad: "Alta", brecha_id: "" };
    expect(datosDelFormulario("controles", valores)).toEqual({
      codigo_control: "GOB-011", pregunta_evaluacion: "¿Algo?", dominio_id: 2, criticidad: "Alta",
    });
  });
  it("valida requeridos, largo y números antes de enviar", () => {
    const e = erroresFormulario("rutas", { ...valoresIniciales("rutas"), horas: "-3" }, true);
    expect(e.nombre).toBeTruthy();
    expect(e.horas).toBeTruthy();
    const largo = erroresFormulario("preguntas_filtro", { ...valoresIniciales("preguntas_filtro"), codigo: "F9",
      orden: "9", pregunta: "x".repeat(501) }, true);
    expect(largo.pregunta).toMatch(/500/);
  });
});

describe("cambios del borrador", () => {
  const dif = {
    total: 3,
    controles: { nuevos: [{ id: -1, etiqueta: "GOB-011", campos: [] }], modificados: [], retirados: [{ id: 5, etiqueta: "GOB-003", campos: [] }], restaurados: [] },
    brechas: { nuevos: [], modificados: [{ id: 1, etiqueta: "ERR-GOB-001", campos: ["criticidad"] }], retirados: [], restaurados: [] },
  };
  it("marca cada fila con su estado", () => {
    const m = estadosDe(dif, "controles");
    expect(m.get(-1)).toBe("nuevo");
    expect(m.get(5)).toBe("retirado");
    expect(estadosDe(dif, "rutas").size).toBe(0);
  });
  it("redacta el resumen con género y número", () => {
    expect(frasesCambios({ controles: { nuevos: 2, retirados: 1 }, brechas: { modificados: 1 } })).toEqual([
      "2 controles nuevos", "1 control retirado", "1 brecha modificada",
    ]);
  });
});

describe("proxy del panel interno · rutas de HU-24", () => {
  it("deja pasar el mantenedor con su método", () => {
    expect(autorizarRutaAdmin("GET", ["admin", "matriz"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["admin", "matriz", "versiones", "3"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "matriz", "borrador"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "matriz", "borrador", "publicar"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "matriz", "borrador", ruta("preguntas_filtro")]).ok).toBe(true);
    expect(autorizarRutaAdmin("PATCH", ["admin", "matriz", "borrador", "controles", "-2"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "matriz", "borrador", "brechas", "4", "retirar"]).ok).toBe(true);
    expect(autorizarRutaAdmin("PATCH", ["admin", "matriz", "borrador", "controles", "12", "aplicabilidad"]).ok).toBe(true);
  });
  it("rechaza métodos, entidades y acciones que no existen", () => {
    expect(autorizarRutaAdmin("PATCH", ["admin", "matriz", "versiones", "3"]).ok).toBe(false);
    expect(autorizarRutaAdmin("POST", ["admin", "matriz", "borrador", "dominios"]).ok).toBe(false);
    expect(autorizarRutaAdmin("POST", ["admin", "matriz", "borrador", "controles", "4", "borrar"]).ok).toBe(false);
    expect(autorizarRutaAdmin("PATCH", ["admin", "matriz", "borrador", "brechas", "4", "aplicabilidad"]).ok).toBe(false);
    expect(autorizarRutaAdmin("GET", ["admin", "matriz", "borrador", "controles", "1", "x", "y"]).ok).toBe(false);
  });
});
