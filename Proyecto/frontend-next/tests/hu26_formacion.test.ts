/**
 * HU-26 (recorrido de módulos y avance) y HU-17 (cerrar brechas con evidencia):
 * lógica pura de presentación y lista blanca del BFF del cliente (sin red ni navegador).
 */
import { describe, expect, it } from "vitest";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  accionModulo,
  faltanPorResponder,
  fechaLarga,
  hrefModulo,
  hrefRemediacion,
  mensajeFormacion,
  resumenAvanceTexto,
  segmentos,
  siguienteLeccion,
} from "@/lib/formacion";
import {
  deltaTexto,
  esperaConsulta,
  estadosDeclarables,
  faseEvidencia,
  mensajeRemediacion,
  resultadoTexto,
  validarArchivo,
} from "@/lib/remediacion";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";
import type { AvanceFormativoApi, EvidenciaRemediacionApi } from "@/lib/types";

const resumen = (o: Partial<AvanceFormativoApi["resumen"]>): AvanceFormativoApi["resumen"] => ({
  modulos_total: 6, iniciados: 3, en_curso: 1, completados: 2, porcentaje: 33.3, horas_total: 30,
  horas_completadas: 8, brechas_total: 5, brechas_con_formacion: 2, porcentaje_brechas_con_formacion: 40, ...o,
});

describe("HU-26 · panel de formación", () => {
  it("la acción de cada módulo depende de su estado", () => {
    expect(accionModulo({ estado: "no_iniciado", lecciones_vistas: 0, lecciones_total: 4 })).toBe("Empezar módulo");
    expect(accionModulo({ estado: "en_curso", lecciones_vistas: 2, lecciones_total: 4 })).toBe("Continuar");
    expect(accionModulo({ estado: "en_curso", lecciones_vistas: 4, lecciones_total: 4 })).toBe("Hacer la actividad");
    expect(accionModulo({ estado: "completado", lecciones_vistas: 4, lecciones_total: 4 })).toBe("Ver módulo y constancia");
  });

  it("el medidor segmentado ordena completados, en curso y pendientes", () => {
    expect(segmentos([{ estado: "no_iniciado" }, { estado: "completado" }, { estado: "en_curso" }, { estado: "completado" }]))
      .toEqual(["completado", "completado", "en_curso", "no_iniciado"]);
    expect(segmentos([])).toEqual([]);
  });

  it("resume el avance en una frase", () => {
    expect(resumenAvanceTexto(resumen({}))).toBe("2 de 6 módulos completados y 1 en curso.");
    expect(resumenAvanceTexto(resumen({ en_curso: 0 }))).toBe("2 de 6 módulos completados.");
    expect(resumenAvanceTexto(resumen({ completados: 6 }))).toBe("Completaste los 6 módulos del plan.");
    expect(resumenAvanceTexto(resumen({ modulos_total: 0, completados: 0 }))).toBe("Tu plan no tiene módulos todavía.");
  });

  it("enlaces al módulo y a cerrar brechas conservan la evaluación", () => {
    expect(hrefModulo(3, 12)).toBe("/panel/capacitacion/3?evaluacion=12");
    expect(hrefModulo(3, null)).toBe("/panel/capacitacion/3");
    expect(hrefRemediacion(12, 40)).toBe("/panel/remediacion?evaluacion=12&control=40");
    expect(hrefRemediacion(null)).toBe("/panel/remediacion");
  });

  it("sigue por la primera lección sin ver y detecta preguntas sin responder", () => {
    expect(siguienteLeccion([{ orden: 1, vista: true }, { orden: 2, vista: false }, { orden: 3, vista: false }])).toBe(2);
    expect(siguienteLeccion([{ orden: 1, vista: true }])).toBeNull();
    const preguntas = [10, 11, 12].map((id) => ({ id, orden: id, enunciado: "", opciones: [] }));
    expect(faltanPorResponder(preguntas, { 10: 0, 12: 1 })).toEqual([11]);
    expect(faltanPorResponder(preguntas, { 10: 0, 11: 0, 12: 0 })).toEqual([]);
  });

  it("la fecha de completado se muestra en hora de Chile", () => {
    expect(fechaLarga("2026-10-27T18:30:00")).toBe("27 de octubre de 2026");
    expect(fechaLarga("2026-01-01T02:00:00")).toBe("31 de diciembre de 2025"); // UTC 02:00 = 23:00 del 31 en Chile
    expect(fechaLarga(null)).toBe("—");
    expect(fechaLarga("no-es-fecha")).toBe("—");
  });

  it("los errores dicen qué pasó y qué hacer", () => {
    const e = (codigo: string, mensaje = "", status = 409) => new ErrorBff(status, { codigo, mensaje });
    expect(mensajeFormacion(e("CONTRATO_NO_VIGENTE", "", 403))).toMatch(/Therion Labs/);
    expect(mensajeFormacion(e("LIMITE_INTENTOS", "Usaste los 5 intentos de hoy.", 429))).toBe("Usaste los 5 intentos de hoy.");
    expect(mensajeFormacion(e("LECCIONES_PENDIENTES"))).toMatch(/lecciones/);
    expect(mensajeFormacion(new Error("x"))).toMatch(/Inténtalo de nuevo/);
  });
});

describe("HU-17 · cerrar brechas con evidencia", () => {
  it("valida tipo, vacío y tamaño antes de subir", () => {
    expect(validarArchivo(null, 10)).toMatch(/Elige/);
    expect(validarArchivo({ name: "foto.PNG", size: 10 }, 10)).toMatch(/PDF/);
    expect(validarArchivo({ name: "acta.pdf", size: 0 }, 10)).toMatch(/vacío/);
    expect(validarArchivo({ name: "acta.pdf", size: 11 * 1024 * 1024 }, 10)).toMatch(/10 MB/);
    for (const n of ["Política.PDF", "acta.docx", "nota.txt"]) expect(validarArchivo({ name: n, size: 100 }, 10)).toBeNull();
  });

  it("solo se declara un estado mejor que el actual", () => {
    expect(estadosDeclarables("no_cumplido")).toEqual(["cumplido", "parcialmente_cumplido"]);
    expect(estadosDeclarables("requiere_revision")).toEqual(["cumplido", "parcialmente_cumplido"]);
    expect(estadosDeclarables("parcialmente_cumplido")).toEqual(["cumplido"]);
  });

  it("resultado de la evidencia", () => {
    const base: EvidenciaRemediacionApi = {
      id_evidencia: 1, respuesta_id: 2, nombre_archivo: "p.pdf", estado_validacion: "pending", estado_declarado: "cumplido",
      estado_previo: "no_cumplido", estado_resultante: null, clasificacion_llm: null, confianza: null,
      justificacion_llm: null, errores_validacion: [], terminos_control: null, fecha_subida: null, fecha_procesada: null,
      en_proceso: true, mejoro: false,
    };
    expect(faseEvidencia(base)).toBe("analizando");
    const mejoro = { ...base, en_proceso: false, mejoro: true, estado_validacion: "validated" as const, estado_resultante: "cumplido" as const };
    expect(faseEvidencia(mejoro)).toBe("mejoro");
    expect(resultadoTexto(mejoro)).toBe("El control pasó de no cumplido a cumplido. Actualizamos tu puntaje.");
    expect(resultadoTexto({ ...mejoro, puntaje_previo: 48.5, puntaje_resultante: 52.1 }))
      .toBe("El control pasó de no cumplido a cumplido. Tu puntaje general subió +3,6 pts.");
    const igual = { ...base, en_proceso: false, estado_validacion: "rejected" as const,
      errores_validacion: ["La evidencia no demuestra un avance respecto del estado actual del control."] };
    expect(faseEvidencia(igual)).toBe("sin-cambio");
    expect(resultadoTexto(igual)).toMatch(/no demuestra un avance/);
    expect(faseEvidencia({ ...igual, estado_validacion: "error" })).toBe("error");
  });

  it("muestra cuánto subió el puntaje", () => {
    expect(deltaTexto(48.5, 52.1)).toBe("+3,6 pts");
    expect(deltaTexto(50, 51)).toBe("+1 pt");
    expect(deltaTexto(50, 50)).toBe("sin cambios");
    expect(deltaTexto(50, 47.5)).toBe("−2,5 pts");
    expect(deltaTexto(null, 50)).toBe("");
  });

  it("consulta el análisis con espera creciente y se detiene", () => {
    expect(esperaConsulta(0)).toBe(1500);
    expect(esperaConsulta(1)).toBeGreaterThan(1500);
    expect(esperaConsulta(30)).toBe(8000);
    expect(esperaConsulta(40)).toBeNull();
  });

  it("mensajes de error de la subida", () => {
    const e = (codigo: string) => new ErrorBff(415, { codigo, mensaje: "" });
    expect(mensajeRemediacion(e("TIPO_NO_ADMITIDO"))).toMatch(/PDF/);
    expect(mensajeRemediacion(e("REMEDIACION_EN_PROCESO"))).toMatch(/análisis/);
    expect(mensajeRemediacion(e("PROMPT_INJECTION"))).toMatch(/instrucciones/);
  });
});

describe("BFF del cliente · rutas de HU-26 y HU-17", () => {
  it("deja pasar el recorrido, la constancia y la remediación", () => {
    expect(autorizarRutaCliente("GET", ["formacion", "avance"]).ok).toBe(true);
    expect(autorizarRutaCliente("GET", ["formacion", "modulos", "3"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["formacion", "modulos", "3", "lecciones", "2", "vista"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["formacion", "modulos", "3", "verificacion"]).ok).toBe(true);
    const constancia = autorizarRutaCliente("GET", ["formacion", "modulos", "3", "constancia"]);
    expect(constancia.ok && constancia.binario).toBe(true);
    expect(autorizarRutaCliente("GET", ["remediacion", "evaluaciones", "12"]).ok).toBe(true);
    const subir = autorizarRutaCliente("POST", ["remediacion", "respuestas", "40", "evidencias"]);
    expect(subir.ok && subir.archivo && subir.conIp).toBe(true);
    expect(autorizarRutaCliente("GET", ["remediacion", "evidencias", "9"]).ok).toBe(true);
  });

  it("no abre métodos ni rutas de más", () => {
    expect(autorizarRutaCliente("GET", ["formacion", "modulos", "3", "verificacion"]).ok).toBe(false); // no se leen respuestas
    expect(autorizarRutaCliente("POST", ["formacion", "avance"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["formacion", "modulos", "3", "constancia"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["respuestas", "40", "evidencias"]).ok).toBe(false); // el cuestionario migrado no se toca
    expect(autorizarRutaCliente("GET", ["remediacion", "evaluaciones", "12", "x"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["formacion", "modulos", "3", "lecciones", "2", "vista", "x"]).ok).toBe(false);
  });
});
