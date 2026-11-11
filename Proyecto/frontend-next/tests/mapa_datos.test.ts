/**
 * Mapa de datos personales: lógica pura del panel (lib/mapaDatos.ts) y lista blanca del proxy.
 */
import { describe, expect, it } from "vitest";
import {
  aplicarFiltros, calcularDisposicion, contieneContacto, csvInventario, desfasesFlujos, describirFiltros, escaparXml,
  esInternacional, filtrosActivos, partirTexto, queryFiltros, rutaFlujo, SIN_FILTROS, svgParaExportar,
  type ElementoMapa, type FlujoMapa, type VistaMapa,
} from "@/lib/mapaDatos";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";
import { filtrarQuery } from "@/lib/servidor/proxy";

function elemento(id: number, tipo: ElementoMapa["tipo"], nombre: string, extra: Partial<ElementoMapa> = {}): ElementoMapa {
  const pais = extra.pais ?? (tipo === "tercero" ? null : "CL");
  return {
    id, tipo, nombre, subtipo: null, descripcion: null, proveedor: null, pais, responsable: null,
    categorias_datos: [], categorias_titulares: [], nna_declarado: false, incluye_nna: false, rol_tercero: null,
    contrato_firmado: null, origen: "manual", clave: null, pendiente_revision: false, fecha_creacion: null,
    fecha_actualizacion: null,
    derivados: { sensibles: [], incluye_nna: false, fuera_de_chile: Boolean(pais && pais !== "CL"), pais_efectivo: pais, flujos_entrantes: 0, flujos_salientes: 0 },
    ...extra,
  };
}

function flujo(id: number, o: number, d: number, extra: Partial<FlujoMapa> = {}, der: Partial<FlujoMapa["derivados"]> = {}): FlujoMapa {
  return {
    id, origen_id: o, destino_id: d, finalidad: null, categorias_datos: [], categorias_titulares: [], nna_declarado: false,
    incluye_nna: false, frecuencia: null, medio: null, cifrado: null, garantia: null, origen: "manual", clave: null,
    pendiente_revision: false, fecha_creacion: null, fecha_actualizacion: null,
    derivados: { internacional: false, pais_origen: "CL", pais_destino: "CL", hacia_tercero: false, desde_tercero: false, sensibles: [], incluye_nna: false, garantia_valida: false, ...der },
    ...extra,
  };
}

const ELEMENTOS = [
  elemento(1, "sistema", "Tienda en línea"),
  elemento(2, "base_datos", "Clientes", { derivados: { sensibles: ["salud"], incluye_nna: true, fuera_de_chile: false, pais_efectivo: "CL", flujos_entrantes: 1, flujos_salientes: 1 }, incluye_nna: true }),
  elemento(3, "tercero", "Proveedor LLM", { pais: "US" }),
  elemento(4, "tercero", "Courier"),
  elemento(5, "sistema", "Aislado"),
];
const FLUJOS = [
  flujo(1, 1, 2),
  flujo(2, 2, 3, { incluye_nna: true }, { internacional: true, pais_destino: "US", sensibles: ["salud"], hacia_tercero: true }),
  flujo(3, 2, 4, {}, { hacia_tercero: true, pais_destino: null }),
];
const VISTA = { elementos: ELEMENTOS, flujos: FLUJOS, mapa: { version: 4, fecha_actualizacion: null, iniciado: true, plantilla_inicial: null } } as unknown as VistaMapa;

describe("disposición del diagrama (misma que el PDF)", () => {
  it("ordena por capas en el sentido de los datos y deja los terceros receptores al final", () => {
    const lay = calcularDisposicion(ELEMENTOS, FLUJOS);
    const col = (id: number) => lay.nodos.get(id)!.columna;
    expect(col(1)).toBe(0);
    expect(col(2)).toBe(1);
    expect(col(3)).toBe(lay.columnas - 1);
    expect(col(4)).toBe(lay.columnas - 1);
    expect(col(5)).toBe(0); // sin flujos: por tipo
    const posiciones = new Set([...lay.nodos.values()].map((n) => `${n.x},${n.y}`));
    expect(posiciones.size).toBe(ELEMENTOS.length);
    expect(lay.ancho).toBeGreaterThan(0);
  });

  it("no se rompe con ciclos ni con un mapa vacío", () => {
    const ciclo = calcularDisposicion([elemento(1, "sistema", "A"), elemento(2, "sistema", "B")], [flujo(1, 1, 2), flujo(2, 2, 1)]);
    expect(new Set([...ciclo.nodos.values()].map((n) => n.columna))).toEqual(new Set([0, 1]));
    expect(calcularDisposicion([], []).columnas).toBe(0);
  });

  it("los flujos hacia atrás rodean y los paralelos no se enciman", () => {
    const lay = calcularDisposicion(ELEMENTOS, FLUJOS);
    const atras = rutaFlujo(lay.nodos.get(2)!, lay.nodos.get(1)!);
    expect(atras.punta.haciaIzquierda).toBe(true);
    const adelante = rutaFlujo(lay.nodos.get(1)!, lay.nodos.get(2)!);
    expect(adelante.punta.haciaIzquierda).toBe(false);
    const d = desfasesFlujos([flujo(1, 1, 2), flujo(2, 2, 1), flujo(3, 1, 2)]);
    expect(new Set([d.get(1), d.get(2), d.get(3)]).size).toBe(3);
  });

  it("parte los nombres largos en dos líneas con puntos suspensivos", () => {
    expect(partirTexto("CRM", 20)).toEqual(["CRM"]);
    const l = partirTexto("Plataforma de comunicación con apoderados y familias del colegio", 20);
    expect(l).toHaveLength(2);
    expect(l[1].endsWith("…")).toBe(true);
    expect(l.every((x) => x.length <= 20)).toBe(true);
  });
});

describe("filtros del mapa navegable", () => {
  it("sin filtros se ve todo", () => {
    const v = aplicarFiltros(VISTA, SIN_FILTROS);
    expect(v.elementos.size).toBe(5);
    expect(v.flujos.size).toBe(3);
    expect(filtrosActivos(SIN_FILTROS)).toBe(0);
  });

  it("dato sensible: el flujo arrastra a sus extremos", () => {
    const v = aplicarFiltros(VISTA, { ...SIN_FILTROS, sensibles: true });
    expect([...v.flujos]).toEqual([2]);
    expect(v.elementos.has(2) && v.elementos.has(3)).toBe(true);
    expect(v.elementos.has(1)).toBe(false);
  });

  it("tercero, país, transferencia internacional, NNA y tipo", () => {
    expect([...aplicarFiltros(VISTA, { ...SIN_FILTROS, tercero: 4 }).flujos]).toEqual([3]);
    const pais = aplicarFiltros(VISTA, { ...SIN_FILTROS, pais: "US" });
    expect(pais.elementos.has(3)).toBe(true);
    expect([...pais.flujos]).toEqual([2]);
    expect([...aplicarFiltros(VISTA, { ...SIN_FILTROS, internacional: true }).flujos]).toEqual([2]);
    expect(aplicarFiltros(VISTA, { ...SIN_FILTROS, nna: true }).elementos.has(2)).toBe(true);
    const terceros = aplicarFiltros(VISTA, { ...SIN_FILTROS, tipo: "tercero" });
    expect(terceros.elementos.has(3) && terceros.elementos.has(4)).toBe(true);
    expect(describirFiltros({ ...SIN_FILTROS, sensibles: true, tercero: 4 }, VISTA, null)).toBe("solo datos sensibles, tercero «Courier»");
  });

  it("arma los parámetros del informe con los mismos nombres del backend", () => {
    expect(queryFiltros(SIN_FILTROS)).toBe("");
    expect(queryFiltros({ ...SIN_FILTROS, sensibles: true, tercero: 3, pais: "US" })).toBe("?sensibles=1&tercero=3&pais=US");
  });
});

describe("reglas espejo del backend", () => {
  it("transferencia internacional: destino fuera de Chile y en otro país", () => {
    expect(esInternacional("CL", "US")).toBe(true);
    expect(esInternacional(null, "US")).toBe(true);
    expect(esInternacional("US", "US")).toBe(false);
    expect(esInternacional("US", "CL")).toBe(false);
    expect(esInternacional("CL", null)).toBe(false);
  });

  it("detecta datos de contacto en los textos (minimización)", () => {
    expect(contieneContacto("ana@empresa.cl")).toBe(true);
    expect(contieneContacto("12.345.678-5")).toBe(true);
    expect(contieneContacto("+56 9 1234 5678")).toBe(true);
    expect(contieneContacto("Jefatura de TI")).toBe(false);
    expect(contieneContacto("SAP S/4HANA 2023")).toBe(false);
  });
});

describe("exportación", () => {
  it("el SVG del PNG escapa lo que escribió el usuario y respeta los filtros", () => {
    const peligroso = { ...VISTA, elementos: [...ELEMENTOS.slice(0, 4), elemento(5, "sistema", "<script>alert(1)</script>")] } as VistaMapa;
    const { svg, ancho, alto } = svgParaExportar(peligroso, SIN_FILTROS, { empresa: "ACME & Cía" });
    expect(svg.startsWith("<svg")).toBe(true);
    expect(svg).not.toContain("<script>");
    expect(svg).toContain("&lt;script&gt;");
    expect(svg).toContain("ACME &amp; Cía");
    expect(ancho).toBeGreaterThan(0);
    expect(alto).toBeGreaterThan(0);
    const filtrado = svgParaExportar(VISTA, { ...SIN_FILTROS, sensibles: true }).svg;
    expect(filtrado).not.toContain("Tienda en línea");
    expect(escaparXml(`"'`)).toBe("&quot;&#39;");
  });

  it("el CSV lleva BOM, separador ; y neutraliza fórmulas de Excel", () => {
    const v = { elementos: [elemento(1, "sistema", "=HYPERLINK(\"x\")")], flujos: [] };
    const csv = csvInventario(v, null);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv.split("\r\n")[0]).toContain('"Registro";');
    expect(csv).toContain("'=HYPERLINK");
  });
});

describe("proxy del cliente", () => {
  const ok = (m: string, r: string) => autorizarRutaCliente(m, r.split("/")).ok;
  it("deja pasar solo las rutas del mapa de datos", () => {
    expect(ok("GET", "mapa-datos")).toBe(true);
    expect(ok("GET", "mapa-datos/catalogo")).toBe(true);
    expect(ok("POST", "mapa-datos/elementos")).toBe(true);
    expect(ok("PATCH", "mapa-datos/flujos/12")).toBe(true);
    expect(ok("DELETE", "mapa-datos/elementos/3")).toBe(true);
    expect(ok("POST", "mapa-datos/sugerencias/llm_externo/aceptar")).toBe(true);
    expect(ok("POST", "mapa-datos/versiones/2/restaurar")).toBe(true);
    expect(ok("POST", "mapa-datos/informe/enviar")).toBe(true);
    const pdf = autorizarRutaCliente("GET", ["mapa-datos", "informe", "pdf"]);
    expect(pdf.ok && pdf.binario).toBe(true);
    expect(ok("DELETE", "mapa-datos")).toBe(false);
    expect(ok("PUT", "mapa-datos/elementos/3")).toBe(false);
    expect(ok("POST", "mapa-datos/sugerencias/../aceptar")).toBe(false);
    expect(ok("GET", "mapa-datos/versiones/abc")).toBe(false);
  });

  it("reenvía la versión y los filtros del informe, nada más", () => {
    expect(filtrarQuery(new URLSearchParams("version=4&sensibles=1&pais=US&token=x"))).toBe("?version=4&sensibles=1&pais=US");
    expect(filtrarQuery(new URLSearchParams("pais=USA"))).toBe("");
  });
});
