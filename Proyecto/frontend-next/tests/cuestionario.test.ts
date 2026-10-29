/**
 * HU-01 / HU-02 · Lógica pura del cuestionario adaptativo (sin red ni navegador).
 */
import { describe, expect, it } from "vitest";
import {
  bloqueosParaCompletar,
  controlesEstimados,
  CONTROLES_BASE,
  CONTROLES_POR_FILTRO,
  cuerpoFiltro,
  errorArchivoEvidencia,
  errorJustificacion,
  ESTADOS,
  ordenarControles,
  preguntasVisibles,
  respuestasFiltroGuardadas,
  type ControlAplicableApi,
  type EstadoFiltroApi,
  type EvidenciaApi,
  type PreguntaFiltroApi,
} from "@/lib/cuestionario/modelo";
import { mensajeDeError } from "@/lib/encuesta/errores";
import { autorizarRuta, cuerpoRespuestaEsDeLaSesion } from "@/lib/servidor/proxy";

const PREGUNTAS: PreguntaFiltroApi[] = ["F1", "F2", "F3", "F4", "F5", "F6", "F7"].map((codigo, i) => ({
  id_pregunta: 10 + i,
  codigo,
  orden: i + 1,
  pregunta: `¿Pregunta ${codigo}?`,
  descripcion: null,
}));

describe("filtro F1–F7 · adapta el cuestionario", () => {
  it("espeja el árbol del backend: 22 base y 40 con todo en Sí", () => {
    expect(CONTROLES_BASE).toBe(22);
    const todoSi = Object.fromEntries(PREGUNTAS.map((p) => [p.codigo, true]));
    expect(controlesEstimados(todoSi)).toBe(40); // los 40 controles de la matriz
    expect(controlesEstimados({ F1: true })).toBe(22);
    expect(controlesEstimados({ F1: true, F4: true, F6: true })).toBe(22 + CONTROLES_POR_FILTRO.F4 + CONTROLES_POR_FILTRO.F6);
  });

  it("F1 = No: ningún control aplica y no se muestran F2..F7", () => {
    expect(controlesEstimados({ F1: false, F2: true })).toBe(0);
    expect(preguntasVisibles(PREGUNTAS, { F1: false }).map((p) => p.codigo)).toEqual(["F1"]);
    expect(preguntasVisibles(PREGUNTAS, { F1: true })).toHaveLength(7);
  });

  it("el cuerpo siempre lleva las 7 respuestas (el backend las exige)", () => {
    const raizNo = cuerpoFiltro(PREGUNTAS, { F1: false, F3: true });
    expect(raizNo.respuestas).toHaveLength(7);
    expect(raizNo.respuestas.every((r) => r.respuesta === false)).toBe(true);
    const mixto = cuerpoFiltro(PREGUNTAS, { F1: true, F3: true });
    expect(mixto.respuestas.filter((r) => r.respuesta).map((r) => r.codigo)).toEqual(["F1", "F3"]);
  });

  it("retoma las respuestas guardadas por pregunta_id", () => {
    const estado: EstadoFiltroApi = {
      evaluacion_id: 1,
      filtro_completado: true,
      fecha_filtro: "2026-10-22",
      preguntas: PREGUNTAS,
      respuestas: [
        { id_respuesta_filtro: 1, pregunta_id: 10, respuesta: true, fecha_respuesta: "2026-10-22" },
        { id_respuesta_filtro: 2, pregunta_id: 13, respuesta: true, fecha_respuesta: "2026-10-22" },
        { id_respuesta_filtro: 3, pregunta_id: 99, respuesta: true, fecha_respuesta: "2026-10-22" },
      ],
      controles_aplicables: 26,
    };
    expect(respuestasFiltroGuardadas(estado)).toEqual({ F1: true, F4: true });
  });
});

describe("respuestas · reglas de HU-02", () => {
  it("justificación obligatoria (≥ 20 con letras) solo en parcial y requiere revisión", () => {
    expect(errorJustificacion("cumplido", "")).toBeNull();
    expect(errorJustificacion("no_cumplido", "")).toBeNull();
    expect(errorJustificacion("parcialmente_cumplido", "corto")).toMatch(/20 caracteres/);
    expect(errorJustificacion("requiere_revision", "1234567890 1234567890 123")).toMatch(/caracteres/);
    expect(errorJustificacion("parcialmente_cumplido", "   Tenemos política pero sin aprobar   ")).toBeNull();
  });

  it("cuenta como el backend: colapsa espacios antes de medir", () => {
    expect(errorJustificacion("parcialmente_cumplido", "a          b          c")).toMatch(/llevas 5/);
  });

  it("evidencia: admitida en cumplido, parcial y revisión; obligatoria solo en revisión", () => {
    const admite = ESTADOS.filter((e) => e.admiteEvidencia).map((e) => e.valor);
    expect(admite.sort()).toEqual(["cumplido", "parcialmente_cumplido", "requiere_revision"]);
    expect(ESTADOS.filter((e) => e.evidenciaObligatoria).map((e) => e.valor)).toEqual(["requiere_revision"]);
  });

  it("formatos de evidencia que el worker puede leer", () => {
    expect(errorArchivoEvidencia({ name: "politica.txt", size: 10 })).toBeNull();
    expect(errorArchivoEvidencia({ name: "Politica.MD", size: 10 })).toBeNull();
    expect(errorArchivoEvidencia({ name: "informe.pdf", size: 10 })).toMatch(/texto/);
    expect(errorArchivoEvidencia({ name: "vacio.txt", size: 0 })).toMatch(/vacío/);
    expect(errorArchivoEvidencia({ name: "grande.txt", size: 13 * 1024 * 1024 })).toMatch(/12 MB/);
  });
});

describe("orden y cierre", () => {
  const ctrl = (id: number, codigo: string, dominio: string): ControlAplicableApi => ({
    id_control: id,
    codigo_control: codigo,
    framework_fuente: null,
    articulo_referencia: null,
    tipo_fuente: null,
    obligacion: null,
    pregunta_evaluacion: null,
    aplicabilidad: null,
    evidencia_esperada: null,
    criticidad: null,
    recomendacion: null,
    dominio: { id: 1, nombre_dominio: dominio },
  });

  it("agrupa por dominio en orden de aparición y luego por código", () => {
    const lista = ordenarControles([ctrl(1, "DAT-003", "Datos"), ctrl(2, "GOB-001", "Gobernanza"), ctrl(3, "DAT-001", "Datos")]);
    expect(lista.map((c) => c.codigo_control)).toEqual(["DAT-001", "DAT-003", "GOB-001"]);
  });

  it("bloquea completar igual que el backend", () => {
    const ev = (estado: string): EvidenciaApi => ({
      id_evidencia: 1,
      nombre_archivo: "e.txt",
      estado_validacion: estado,
      clasificacion_llm: null,
      confianza: null,
      justificacion_llm: null,
      errores_validacion: null,
      fecha_subida: null,
      fecha_procesada: null,
    });
    const base = { id_control: 0, codigo_control: "", dominio_id: 1, dominio: "D" };
    const progreso = {
      pendientes: [{ ...base, id_control: 1, codigo_control: "A-1" }],
      respondidos: [
        { ...base, id_control: 2, codigo_control: "A-2", id_respuesta: 20, estado_clasificacion: "requiere_revision", estado_clasificacion_final: null },
        { ...base, id_control: 3, codigo_control: "A-3", id_respuesta: 30, estado_clasificacion: "cumplido", estado_clasificacion_final: null },
        { ...base, id_control: 4, codigo_control: "A-4", id_respuesta: 40, estado_clasificacion: "requiere_revision", estado_clasificacion_final: null },
      ],
    };
    const evidencias = new Map([
      [30, [ev("processing")]],
      [40, [ev("validated")]],
    ]);
    const b = bloqueosParaCompletar(progreso, evidencias);
    expect(b.map((x) => `${x.tipo}:${x.codigo}`).sort()).toEqual([
      "evidencia-en-curso:A-3",
      "pendiente:A-1",
      "revision-sin-evidencia:A-2",
    ]);
    expect(bloqueosParaCompletar({ pendientes: [], respondidos: [progreso.respondidos[2]] }, evidencias)).toEqual([]);
  });
});

describe("BFF · el cuestionario solo usa rutas permitidas", () => {
  const ok = (metodo: string, ruta: string) => autorizarRuta(metodo, ruta.split("/"), 7).ok;

  it("permite todo lo que llama el cuestionario y el panel del encuestado", () => {
    for (const [m, r] of [
      ["GET", "evaluaciones/7/filtro"],
      ["POST", "evaluaciones/7/filtro"],
      ["GET", "evaluaciones/7/controles-aplicables"],
      ["GET", "evaluaciones/7/progreso"],
      ["POST", "respuestas"],
      ["GET", "respuestas/55"],
      ["POST", "respuestas/55/evidencias"],
      ["GET", "evidencias/9"],
      ["POST", "evaluaciones/7/completar"],
      ["GET", "evaluaciones/7"],
      ["GET", "evaluaciones/7/resumen"],
      ["GET", "evaluaciones/7/comparativa"],
      ["GET", "evaluaciones/7/respuestas"],
      ["GET", "brechas"],
      ["GET", "controles"],
    ]) {
      expect(ok(m, r), `${m} ${r}`).toBe(true);
    }
  });

  it("no deja tocar otra evaluación", () => {
    expect(ok("POST", "evaluaciones/8/completar")).toBe(false);
    expect(ok("GET", "evaluaciones/8/resumen")).toBe(false);
    expect(cuerpoRespuestaEsDeLaSesion({ evaluacion_id: 8, matriz_control_id: 1 }, 7)).toBe(false);
  });
});

describe("errores del cuestionario", () => {
  it("no muestra al usuario los códigos internos que trae el detalle del backend", () => {
    const m = mensajeDeError({ codigo: "CUESTIONARIO_INCOMPLETO", mensaje: "Faltan 2 de 28 controles por responder: DAT-001, GOB-003" });
    expect(m.titulo).toMatch(/quedan preguntas/);
    expect(m.detalle).not.toMatch(/DAT-001|GOB-003/);
    expect(`${m.titulo} ${m.detalle}`).not.toMatch(/control/i);
  });

  it("prompt injection en la justificación tiene un mensaje propio", () => {
    expect(mensajeDeError({ codigo: "PROMPT_INJECTION", mensaje: "x" }).titulo).toMatch(/No pudimos guardar/);
  });
});
