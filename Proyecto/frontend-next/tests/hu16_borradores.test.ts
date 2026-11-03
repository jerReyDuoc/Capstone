/**
 * HU-16 · Borradores de cumplimiento: lista blanca del proxy del cliente, vista previa segura
 * del Markdown, campos pendientes y textos de presentación (lógica pura).
 */
import { describe, expect, it } from "vitest";
import {
  advertenciasVisibles, cuotaBorradoresTexto, ETIQUETA_TIPO, parsearMarkdown, pendientesDe, rutaDescargaBorrador,
  segmentos, siguientePendiente, validarContenido,
} from "@/lib/borradores";
import { filtrarQuery } from "@/lib/servidor/proxy";
import { autorizarRutaCliente, TIPOS_BORRADOR } from "@/lib/servidor/proxyCliente";

describe("HU-16 · proxy del cliente", () => {
  it("deja generar, revisar, editar, descargar, consolidar y descartar", () => {
    expect(autorizarRutaCliente("GET", ["borradores", "plantillas"]).ok).toBe(true);
    expect(autorizarRutaCliente("GET", ["borradores"]).ok).toBe(true);
    const generar = autorizarRutaCliente("POST", ["borradores"]);
    expect(generar.ok && generar.timeoutMs).toBe(90_000); // espera al Agente IA
    expect(autorizarRutaCliente("GET", ["borradores", "7"]).ok).toBe(true);
    expect(autorizarRutaCliente("PATCH", ["borradores", "7"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["borradores", "7"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["borradores", "7", "consolidacion"]).ok).toBe(true);
    const descarga = autorizarRutaCliente("GET", ["borradores", "7", "descarga"]);
    expect(descarga.ok && descarga.binario).toBe(true);
    expect(descarga.ok && descarga.tipos).toEqual(TIPOS_BORRADOR);
  });

  it("deja fuera lo que no corresponde", () => {
    expect(autorizarRutaCliente("PATCH", ["borradores"]).ok).toBe(false);
    expect(autorizarRutaCliente("DELETE", ["borradores"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["borradores", "7"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["borradores", "x", "descarga"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["borradores", "7", "descarga"]).ok).toBe(false);
  });

  it("el formato de la descarga pasa por el filtro de la consulta", () => {
    expect(filtrarQuery(new URLSearchParams("formato=md&token=x"))).toBe("?formato=md");
    expect(filtrarQuery(new URLSearchParams("formato=markdown"))).toBe("");
    expect(rutaDescargaBorrador(7, "pdf")).toBe("/bff/cliente/api/borradores/7/descarga?formato=pdf");
  });
});

describe("HU-16 · vista previa del Markdown", () => {
  const md = [
    "# Política de uso de IA",
    "",
    "**ACME SpA** · RUT 76.086.428-5",
    "",
    "> **BORRADOR.** Revisa con tu asesor legal.",
    "",
    "## 1. Objetivo",
    "",
    "Esta política aplica a",
    "todo el personal.",
    "",
    "- uno",
    "- dos",
    "1. primero",
    "2. segundo",
    "",
    "| Campo | Detalle |",
    "|---|---|",
    "| Responsable | [COMPLETAR: cargo] |",
    "---",
  ].join("\n");

  it("arma los bloques del mismo subconjunto que el PDF", () => {
    const b = parsearMarkdown(md);
    expect(b.map((x) => x.tipo)).toEqual(["titulo", "parrafo", "cita", "titulo", "parrafo", "lista", "lista", "tabla", "separador"]);
    expect(b[4]).toEqual({ tipo: "parrafo", texto: "Esta política aplica a todo el personal." });
    expect(b[5]).toEqual({ tipo: "lista", ordenada: false, items: ["uno", "dos"] });
    expect(b[6]).toEqual({ tipo: "lista", ordenada: true, items: ["primero", "segundo"] });
    expect(b[7]).toEqual({ tipo: "tabla", cabecera: ["Campo", "Detalle"], filas: [["Responsable", "[COMPLETAR: cargo]"]] });
  });

  it("el HTML que escribe el usuario queda como texto", () => {
    const g = segmentos('<img src=x onerror="alert(1)"> **ok** *nota* `x` [COMPLETAR: fecha]');
    expect(g).toEqual([
      { tipo: "texto", texto: '<img src=x onerror="alert(1)"> ' },
      { tipo: "negrita", texto: "ok" },
      { tipo: "texto", texto: " " },
      { tipo: "cursiva", texto: "nota" },
      { tipo: "texto", texto: " " },
      { tipo: "codigo", texto: "x" },
      { tipo: "texto", texto: " " },
      { tipo: "pendiente", texto: "[COMPLETAR: fecha]" },
    ]);
  });
});

describe("HU-16 · revisión", () => {
  it("cuenta los campos pendientes sin repetir y los recorre en orden", () => {
    const t = "A [COMPLETAR: cargo] B [COMPLETAR: fecha] C [COMPLETAR: cargo]";
    expect(pendientesDe(t)).toEqual(["[COMPLETAR: cargo]", "[COMPLETAR: fecha]"]);
    const p1 = siguientePendiente(t, 0);
    expect(p1 && t.slice(p1.inicio, p1.fin)).toBe("[COMPLETAR: cargo]");
    const p2 = siguientePendiente(t, p1!.fin);
    expect(p2 && t.slice(p2.inicio, p2.fin)).toBe("[COMPLETAR: fecha]");
    // Al final vuelve al primero
    expect(siguientePendiente(t, t.length)?.inicio).toBe(p1!.inicio);
    expect(siguientePendiente("sin marcadores", 0)).toBeNull();
  });

  it("valida el contenido antes de guardar", () => {
    expect(validarContenido("   ", 100).ok).toBe(false);
    expect(validarContenido("x".repeat(101), 100).ok).toBe(false);
    expect(validarContenido("# Política", 100).ok).toBe(true);
  });

  it("muestra solo las advertencias útiles para el usuario", () => {
    expect(advertenciasVisibles(["ia_no_disponible", "clausula_desconocida", "ia_no_disponible", "url"])).toEqual([
      "Se armó sin el Agente IA: el servicio no respondió.",
      "Quitamos enlaces externos que propuso el Agente IA.",
    ]);
    expect(advertenciasVisibles([])).toEqual([]);
  });

  it("textos de la cuota y de las plantillas, sin códigos internos", () => {
    expect(cuotaBorradoresTexto({ usados: 3, limite: 10, restantes: 7, reinicia_en: "" })).toBe("Quedan 7 de 10 borradores con IA hoy.");
    expect(cuotaBorradoresTexto({ usados: 10, limite: 10, restantes: 0, reinicia_en: "" })).toContain("usó los borradores");
    expect(cuotaBorradoresTexto({ usados: 0, limite: null, restantes: null, reinicia_en: "" })).toBe("");
    expect(Object.values(ETIQUETA_TIPO).join(" ")).not.toMatch(/(DAT|GOB|RIE|SEG)-\d{3}/);
  });
});
