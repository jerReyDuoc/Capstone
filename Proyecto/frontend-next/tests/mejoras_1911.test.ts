/**
 * Mejoras 19-11:
 *   1. Campo de contraseña con botón mostrar/ocultar (PasswordInput).
 *   2. Geometría del radar de madurez.
 *   4. Cumplimiento por normativa del Plan de acción (fórmula, normativas reales, brechas por tipo).
 *   5. Generador de documentos: brecha → documento, relación en el historial, textos sin códigos internos.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PasswordInput, textosVisibilidad } from "@/components/ui/PasswordInput";
import {
  brechasPorTipo, calcularCumplimiento, filtrarPorNormativa, formatoPorcentaje, normativaDe, porcentajeCumplimiento,
  responsableSugerido,
} from "@/lib/cumplimientoNormativa";
import { panelDemo } from "@/lib/demo";
import {
  agregarRelacion, brechaPendienteValida, ESTADO_HISTORIAL, hrefGenerarDocumento, hrefVolverABrecha, MAX_RELACIONES,
  parsearRelaciones, plantillaParaBrecha, PREFIJO_ALMACEN_DOCUMENTOS, PRESENTACION_PLANTILLA, REPORTES, relacionDesdeBrecha,
  type BrechaRelacionada,
} from "@/lib/generadorDocumentos";
import { anclaEtiqueta, partirEtiqueta, poligonoRadar, puntoEnEje } from "@/lib/radar";
import { PREFIJOS_DE_CUENTA } from "@/lib/sesionNavegador";
import type { ControlApi, EstadoClasificacion, RespuestaApi } from "@/lib/types";

/* ------------------------------------------------------------ 1. contraseña */
describe("Mostrar u ocultar la contraseña", () => {
  it("alterna tipo, texto accesible e ícono", () => {
    expect(textosVisibilidad(false)).toEqual({ type: "password", etiqueta: "Mostrar contraseña", icono: "ojo" });
    expect(textosVisibilidad(true)).toEqual({ type: "text", etiqueta: "Ocultar contraseña", icono: "ojoTachado" });
  });

  it("parte oculta, con un botón que no envía el formulario y apunta al campo", () => {
    const html = renderToStaticMarkup(
      createElement(PasswordInput, { id: "pw", autoComplete: "current-password", className: "input", defaultValue: "secreta1" }),
    );
    expect(html).toContain('type="password"');
    expect(html).toContain('autoComplete="current-password"');
    expect(html).toContain('class="input"');
    expect(html).toMatch(/<button[^>]*type="button"/);
    expect(html).toContain('aria-label="Mostrar contraseña"');
    expect(html).toContain('aria-controls="pw"');
    // Las props del input no van a parar al botón ni se pierden
    expect(html).toContain('id="pw"');
    expect(html).not.toMatch(/<button[^>]*autoComplete/);
  });

  it("un campo desactivado desactiva también el botón", () => {
    const html = renderToStaticMarkup(createElement(PasswordInput, { id: "pw2", disabled: true }));
    expect(html).toMatch(/<input[^>]*disabled/);
    expect(html).toMatch(/<button[^>]*disabled/);
  });
});

/* ------------------------------------------------------------ 2. radar */
describe("Geometría del radar", () => {
  it("con 4 dimensiones forma un rombo: arriba, derecha, abajo, izquierda", () => {
    expect(puntoEnEje(100, 100, 50, 100, 0, 4)).toEqual({ x: 100, y: 50 });
    expect(puntoEnEje(100, 100, 50, 100, 1, 4)).toEqual({ x: 150, y: 100 });
    expect(puntoEnEje(100, 100, 50, 100, 2, 4)).toEqual({ x: 100, y: 150 });
    expect(puntoEnEje(100, 100, 50, 100, 3, 4)).toEqual({ x: 50, y: 100 });
  });

  it("los valores se limitan a 0-100 y el polígono tiene un vértice por eje", () => {
    expect(puntoEnEje(0, 0, 10, 250, 0, 4)).toEqual({ x: 0, y: -10 });
    expect(puntoEnEje(0, 0, 10, -5, 0, 4)).toEqual({ x: 0, y: 0 });
    expect(poligonoRadar([50, 50, 50, 50], 100, 100, 100)).toBe("100,50 150,100 100,150 50,100");
  });

  it("las etiquetas se alinean según el lado y se parten sin cortar palabras", () => {
    expect([0, 1, 2, 3].map((i) => anclaEtiqueta(i, 4))).toEqual(["middle", "start", "middle", "end"]);
    expect(partirEtiqueta("Protección de Datos")).toEqual(["Protección de", "Datos"]);
    expect(partirEtiqueta("Uso Responsable")).toEqual(["Uso", "Responsable"]);
    expect(partirEtiqueta("Gobernanza de IA")).toEqual(["Gobernanza", "de IA"]);
    expect(partirEtiqueta("Ética")).toEqual(["Ética"]);
    expect(partirEtiqueta("una dos tres cuatro cinco seis siete ocho", 5).length).toBeLessThanOrEqual(3);
  });
});

/* ------------------------------------------------------------ 4. cumplimiento por normativa */
const control = (id: number, framework: string | null): ControlApi => ({
  id_control: id, codigo_control: null, framework_fuente: framework, obligacion: null, criticidad: null, recomendacion: null, dominio: null,
});
const respuesta = (id: number, controlId: number, estado: EstadoClasificacion | null, final: EstadoClasificacion | null = null): RespuestaApi => ({
  id_respuesta: id, estado_clasificacion: estado, estado_clasificacion_final: final, fuente_clasificacion: null,
  confianza_clasificacion: null, fecha_validacion: null, matriz_controles_id_control: controlId, catalogo_brechas_id_brecha: null,
});

describe("Cumplimiento por normativa", () => {
  const controles = [
    control(1, "Ley N.º 21.719"), control(2, "Ley N.º 21.719"), control(3, "Ley N.º 21.719"), control(4, "Ley N.º 21.719"),
    control(5, "ISO/IEC 42001"), control(6, "ISO/IEC 42001"),
    control(7, "NIST AI RMF 100-1"), control(8, "NIST AI RMF 100-1"),
    control(9, "OWASP LLM"),
  ];
  const respuestas = [
    respuesta(1, 1, "cumplido"),
    respuesta(2, 2, "parcialmente_cumplido"),
    respuesta(3, 3, "no_cumplido"),
    respuesta(4, 4, "no_aplica"), // no entra al cálculo
    respuesta(5, 5, "no_cumplido", "cumplido"), // el estado final manda
    respuesta(6, 6, "requiere_revision"), // cuenta como 0 hasta resolverse
    respuesta(7, 7, "no_aplica"),
    respuesta(8, 8, "no_aplica"), // NIST: todo "no aplica" → no se muestra
    respuesta(9, 9, "parcialmente_cumplido"),
    respuesta(10, 99, "cumplido"), // control fuera de la matriz: solo cuenta en el general
  ];
  const c = calcularCumplimiento(respuestas, controles);

  it("aplica la fórmula (cumplido 1, parcial 0,5) sobre lo evaluado, sin 'no aplica'", () => {
    const ley = c.normativas.find((n) => n.id === "ley-21719")!;
    expect(ley).toMatchObject({ cumplidos: 1, parciales: 1, noCumplidos: 1, noAplica: 1, evaluados: 3 });
    expect(ley.porcentaje).toBe(50); // (1 + 0,5) / 3
    const iso = c.normativas.find((n) => n.id === "iso-42001")!;
    expect(iso).toMatchObject({ cumplidos: 1, enRevision: 1, evaluados: 2, porcentaje: 50 });
    expect(c.normativas.find((n) => n.id === "owasp-llm")?.porcentaje).toBe(50);
  });

  it("el general usa la misma fórmula con todas las respuestas evaluadas", () => {
    // cumplidos 3 (1, 5, 10), parciales 2 (2, 9), no cumplido 1, en revisión 1 → (3 + 1) / 7
    expect(c.general).toMatchObject({ cumplidos: 3, parciales: 2, noCumplidos: 1, enRevision: 1, evaluados: 7 });
    expect(c.general.porcentaje).toBe(57.1);
  });

  it("solo muestra normativas con controles evaluados y en orden fijo; no inventa las que faltan", () => {
    expect(c.normativas.map((n) => n.nombre)).toEqual(["Ley 21.719", "ISO/IEC 42001", "OWASP LLM"]);
    expect(c.normativas.some((n) => n.id === "iso-27001" || n.id === "iso-23894")).toBe(false);
  });

  it("reconoce los nombres de la matriz y conserva los desconocidos", () => {
    expect(normativaDe("Ley N.º 21.719")?.id).toBe("ley-21719");
    expect(normativaDe("NIST AI RMF 100-1")?.nombre).toBe("NIST AI RMF");
    expect(normativaDe("NIST 600-1")?.id).toBe("nist-ai-600");
    expect(normativaDe("ISO/IEC 27001:2022")?.id).toBe("iso-27001");
    expect(normativaDe("Norma Interna X")).toMatchObject({ id: "norma-interna-x", nombre: "Norma Interna X" });
    expect(normativaDe(null)).toBeNull();
    expect(normativaDe("  ")).toBeNull();
  });

  it("sin nada evaluado no hay porcentaje", () => {
    expect(porcentajeCumplimiento({ cumplidos: 0, parciales: 0, noCumplidos: 0, enRevision: 0 })).toBeNull();
    expect(formatoPorcentaje(null)).toBe("—");
    expect(formatoPorcentaje(57.1)).toBe("57,1 %");
  });

  it("brechas por tipo: cada brecha en un solo grupo (la crítica solo en Crítico)", () => {
    const t = brechasPorTipo(5, [
      { estado: "no_cumplido", severidad: "Crítica" },
      { estado: "no_cumplido", severidad: "Alta" },
      { estado: "parcialmente_cumplido", severidad: "Media" },
      { estado: "parcialmente_cumplido", severidad: "Crítica" },
    ]);
    expect(t).toEqual({ cumple: 5, parcial: 1, noCumple: 1, critico: 2 });
  });

  it("filtra las brechas por normativa a través del control", () => {
    const brechas = [{ controlId: 1 }, { controlId: 5 }, { controlId: null }];
    expect(filtrarPorNormativa(brechas, "ley-21719", c.normativaPorControl)).toEqual([{ controlId: 1 }]);
    expect(filtrarPorNormativa(brechas, null, c.normativaPorControl)).toHaveLength(3);
  });

  it("el panel demo trae el desglose calculado y coherente con sus brechas", () => {
    const p = panelDemo(9101);
    expect(p.cumplimiento?.normativas.map((n) => n.id)).toEqual(["ley-21719", "iso-42001", "nist-ai-rmf", "nist-ai-600", "owasp-llm"]);
    const g = p.cumplimiento!.general;
    expect(g.noCumplidos + g.parciales).toBe(p.brechas.length);
    for (const n of p.cumplimiento!.normativas) expect(n.porcentaje).toBeGreaterThanOrEqual(0);
  });

  it("sugiere un responsable por dimensión", () => {
    expect(responsableSugerido("Protección de Datos")).toBe("Encargado de Datos");
    expect(responsableSugerido("Otra")).toBe("Oficial de Cumplimiento");
  });
});

/* ------------------------------------------------------------ 5. generador de documentos */
describe("Generador de documentos", () => {
  it("elige el documento que ayuda a cerrar cada brecha", () => {
    expect(plantillaParaBrecha({ controlCodigo: "DAT-002", codigo: "ERR-DAT-002" })).toBe("pia");
    expect(plantillaParaBrecha({ controlCodigo: null, codigo: "ERR-DAT-010" })).toBe("aviso_privacidad");
    expect(plantillaParaBrecha({ controlCodigo: "GOB-003", codigo: "x" })).toBe("politica_llm");
    expect(plantillaParaBrecha({ controlCodigo: null, codigo: "ERR-DAT-099" })).toBe("aviso_privacidad");
    expect(plantillaParaBrecha({ controlCodigo: null, codigo: "RESP-12" })).toBe("politica_llm");
  });

  it("arma el enlace desde la brecha y el de vuelta al plan de acción", () => {
    expect(hrefGenerarDocumento({ respuestaId: 501, controlCodigo: "DAT-002", codigo: "ERR-DAT-002" }, 9101))
      .toBe("/empresa/borradores?plantilla=pia&brecha=501&evaluacion=9101");
    const r = relacionDesdeBrecha({ respuestaId: 501, prioridad: 3, descripcion: "x".repeat(400) }, 9101);
    expect(r.descripcion).toHaveLength(240);
    expect(hrefVolverABrecha(r)).toBe("/panel/brechas?evaluacion=9101&q=%233");
  });

  const rel: BrechaRelacionada = { respuestaId: 501, evaluacionId: 9101, prioridad: 3, descripcion: "Sin aviso de privacidad" };

  it("lee la relación guardada e ignora lo que no tiene la forma esperada", () => {
    const texto = JSON.stringify({ 7: rel, 8: { respuestaId: "x" }, nope: rel });
    expect(parsearRelaciones(texto)).toEqual({ 7: rel });
    expect(parsearRelaciones("{no es json")).toEqual({});
    expect(parsearRelaciones(null)).toEqual({});
  });

  it("guarda como máximo las relaciones más recientes", () => {
    let mapa: Record<number, BrechaRelacionada> = {};
    for (let i = 1; i <= MAX_RELACIONES + 5; i++) mapa = agregarRelacion(mapa, i, rel);
    const ids = Object.keys(mapa).map(Number);
    expect(ids).toHaveLength(MAX_RELACIONES);
    expect(Math.min(...ids)).toBe(6);
  });

  it("la brecha pendiente solo vale si es la que pide la URL", () => {
    const texto = JSON.stringify(rel);
    expect(brechaPendienteValida(texto, 501)).toEqual(rel);
    expect(brechaPendienteValida(texto, 502)).toBeNull();
    expect(brechaPendienteValida(texto, null)).toBeNull();
    expect(brechaPendienteValida("basura", 501)).toBeNull();
  });

  it("la relación se borra al cerrar sesión (es dato de la cuenta)", () => {
    expect(PREFIJOS_DE_CUENTA).toContain(PREFIJO_ALMACEN_DOCUMENTOS);
  });

  it("estados del historial en lenguaje simple", () => {
    expect(ESTADO_HISTORIAL.en_revision.texto).toBe("Borrador");
    expect(ESTADO_HISTORIAL.consolidado.texto).toBe("Final");
  });

  it("los textos visibles no usan códigos internos", () => {
    const textos = [
      ...REPORTES.flatMap((r) => [r.titulo, r.descripcion, r.ayuda, ...r.incluye]),
      ...Object.values(PRESENTACION_PLANTILLA).flatMap((p) => [p.titulo, p.resumen, ...p.incluye]),
    ].join(" ");
    expect(textos).not.toMatch(/\b(HU|T)-\d+|(DAT|GOB|RIE|SEG)-\d{3}/);
  });
});
