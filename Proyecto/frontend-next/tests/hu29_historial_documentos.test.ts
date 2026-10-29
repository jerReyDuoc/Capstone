/**
 * HU-29 · "Mis evaluaciones" (historial, evolución y reevaluación) y "Mis documentos".
 * Lógica pura: lista blanca del proxy del cliente, rutas de documentos y formatos.
 */
import { describe, expect, it } from "vitest";
import { baseCuestionario, usarBaseCuestionario } from "@/lib/cuestionario/api";
import { COLORES_DIMENSION, nombreDesdeDisposicion, rutaDocumento, tamanoLegible, textoVariacion } from "@/lib/empresa";
import { parseErrorBackend } from "@/lib/encuesta/contratos";
import { autorizarRutaCliente, TIPOS_DOCUMENTO } from "@/lib/servidor/proxyCliente";

describe("HU-29 · proxy del cliente", () => {
  it("deja leer el historial e iniciar una reevaluación", () => {
    expect(autorizarRutaCliente("GET", ["cliente", "evaluaciones"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["cliente", "evaluaciones"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["cliente", "evaluaciones"]).ok).toBe(false);
  });

  it("deja responder la reevaluación con las rutas del cuestionario", () => {
    for (const sub of ["filtro", "controles-aplicables", "progreso"]) {
      expect(autorizarRutaCliente("GET", ["evaluaciones", "30", sub]).ok).toBe(true);
    }
    expect(autorizarRutaCliente("POST", ["evaluaciones", "30", "filtro"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["evaluaciones", "30", "completar"]).ok).toBe(true);
    // FastAPI define POST /api/respuestas/ con barra final
    const r = autorizarRutaCliente("POST", ["respuestas"]);
    expect(r.ok && r.ruta).toBe("respuestas/");
    expect(autorizarRutaCliente("GET", ["respuestas", "40"]).ok).toBe(true);
    const subir = autorizarRutaCliente("POST", ["respuestas", "40", "evidencias"]);
    expect(subir.ok && subir.archivo && subir.conIp).toBe(true);
    expect(autorizarRutaCliente("GET", ["evidencias", "9"]).ok).toBe(true);
    // Lo que no corresponde sigue fuera
    expect(autorizarRutaCliente("POST", ["evaluaciones", "30", "cerrar"]).ok).toBe(false);
    expect(autorizarRutaCliente("PUT", ["respuestas", "40"]).ok).toBe(false);
    expect(autorizarRutaCliente("DELETE", ["respuestas", "40"]).ok).toBe(false);
  });

  it("Mis documentos: listar, archivar, descargar binarios y eliminar", () => {
    expect(autorizarRutaCliente("GET", ["cliente", "documentos"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["cliente", "documentos", "informes"]).ok).toBe(true);
    for (const ruta of [["cliente", "documentos", "5", "descarga"], ["cliente", "documentos", "evidencias", "7", "descarga"]]) {
      const a = autorizarRutaCliente("GET", ruta);
      expect(a.ok && a.binario).toBe(true);
      expect(a.ok && a.tipos).toEqual(TIPOS_DOCUMENTO);
    }
    expect(autorizarRutaCliente("DELETE", ["cliente", "documentos", "5"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["cliente", "documentos", "evidencias", "7"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["cliente", "documentos", "constancias", "3"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["cliente", "documentos", "informes"]).ok).toBe(false);
    expect(autorizarRutaCliente("DELETE", ["cliente", "documentos", "otros", "3"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["cliente", "documentos", "5", "descarga"]).ok).toBe(false);
    // El informe PDF de siempre sigue aceptando solo PDF
    const pdf = autorizarRutaCliente("GET", ["evaluaciones", "12", "informe", "pdf"]);
    expect(pdf.ok && pdf.tipos).toBeUndefined();
  });
});

describe("HU-29 · utilidades", () => {
  it("arma la ruta del BFF de cada documento", () => {
    expect(rutaDocumento("documento", 5, "descarga")).toBe("/bff/cliente/api/cliente/documentos/5/descarga");
    expect(rutaDocumento("documento", 5, "eliminar")).toBe("/bff/cliente/api/cliente/documentos/5");
    expect(rutaDocumento("evidencia", 7, "descarga")).toBe("/bff/cliente/api/cliente/documentos/evidencias/7/descarga");
    expect(rutaDocumento("constancia", 3, "descarga")).toBe("/bff/cliente/api/formacion/modulos/3/constancia");
    expect(rutaDocumento("constancia", 3, "eliminar")).toBe("/bff/cliente/api/cliente/documentos/constancias/3");
  });

  it("lee el nombre de descarga solo si es seguro", () => {
    expect(nombreDesdeDisposicion('attachment; filename="informe_evaluacion-3_2026-10-29_101500.pdf"', "x"))
      .toBe("informe_evaluacion-3_2026-10-29_101500.pdf");
    expect(nombreDesdeDisposicion(null, "documento-1")).toBe("documento-1");
  });

  it("formatea la variación y el tamaño", () => {
    expect(textoVariacion(12.5)).toBe("+12,5");
    expect(textoVariacion(-3)).toBe("−3");
    expect(textoVariacion(0.01)).toBe("sin cambio");
    expect(textoVariacion(null)).toBe("—");
    expect(tamanoLegible(800)).toBe("800 B");
    expect(tamanoLegible(2048)).toBe("2 KB");
    expect(tamanoLegible(1.5 * 1024 * 1024)).toBe("1,5 MB");
  });

  it("409 EVALUACION_EN_CURSO trae la evaluación para retomarla", () => {
    const e = parseErrorBackend(409, { detail: { codigo: "EVALUACION_EN_CURSO", mensaje: "x", evaluacion_id: 31 } });
    expect(e.codigo).toBe("EVALUACION_EN_CURSO");
    expect(e.evaluacionId).toBe(31);
    expect(parseErrorBackend(409, { detail: { codigo: "X", evaluacion_id: "31" } }).evaluacionId).toBeUndefined();
  });

  it("el cuestionario cambia de BFF para el cliente", () => {
    expect(baseCuestionario()).toBe("/bff/api");
    usarBaseCuestionario("/bff/cliente/api");
    expect(baseCuestionario()).toBe("/bff/cliente/api");
    usarBaseCuestionario("/bff/api");
  });

  it("paleta de dimensiones: 5 colores fijos y distintos", () => {
    expect(new Set(COLORES_DIMENSION).size).toBe(5);
  });
});
