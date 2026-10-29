/**
 * HU-15 · Agente IA Tutor: lógica pura de presentación y lista blanca del BFF del cliente
 * (sin red ni navegador). La lógica de negocio (contexto aislado, anonimización, cuota) se
 * prueba en el backend: tests/test_hu15_tutor.py.
 */
import { describe, expect, it } from "vitest";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";
import {
  conversacionParaRetomar,
  cuotaTexto,
  horaCorta,
  mensajeProvisional,
  mensajeTutor,
  parrafos,
  preguntaPaso,
  sugerenciasIniciales,
  TIPO_RESPUESTA,
  tutorSinServicio,
  validarMensaje,
} from "@/lib/tutor";
import type { BrechaTutorApi, ContextoTutorApi, ConversacionTutorApi } from "@/lib/types";

const brecha = (o: Partial<BrechaTutorApi>): BrechaTutorApi => ({
  ref: "DAT-001", codigo: "BR-001", control_codigo: "DAT-001", dominio: "Protección de Datos",
  descripcion: "x", severidad: "Alta", estado: "no_cumplido", accion: null, prioridad: 1, respuesta_id: 10,
  ruta_id: 1, ruta_nombre: "Ruta", ruta_nivel: "Inicial", formacion_completada: false, ...o,
});

const contexto = (o: Partial<ContextoTutorApi> = {}): ContextoTutorApi => ({
  evaluacion_id: 7, fecha_evaluacion: "2026-10-01", puntaje_general: 40, nivel_madurez: "en_desarrollo",
  nivel_sugerido: "Intermedio", brechas_total: 2, brechas_por_estado: {}, brechas_por_severidad: {},
  brechas: [brecha({ ref: "GOB-002", prioridad: 2 }), brecha({ ref: "DAT-001", prioridad: 1 })],
  foco: null, niveles: ["Inicial", "Intermedio", "Avanzado"], ...o,
});

const conv = (o: Partial<ConversacionTutorApi>): ConversacionTutorApi => ({
  id: 1, titulo: null, nivel: "Inicial", evaluacion_id: 7, ruta_id: null, mensajes_total: 0,
  fecha_creacion: null, fecha_ultimo_mensaje: null, estado: "activa", ...o,
});

describe("HU-15 · validación y textos", () => {
  it("valida el mensaje antes de gastar cuota", () => {
    expect(validarMensaje("   ")).toEqual({ ok: false, motivo: "Escribe tu pregunta para el tutor." });
    expect(validarMensaje("x".repeat(2001)).ok).toBe(false);
    expect(validarMensaje("x".repeat(11), 10).ok).toBe(false);
    expect(validarMensaje("  ¿qué hago?  ")).toEqual({ ok: true, texto: "¿qué hago?" });
  });

  it("explica la cuota diaria de la empresa", () => {
    expect(cuotaTexto({ usados: 3, limite: 60, restantes: 57, reinicia_en: "" })).toBe("Te quedan 57 mensajes de 60 hoy.");
    expect(cuotaTexto({ usados: 59, limite: 60, restantes: 1, reinicia_en: "" })).toBe("Te queda 1 mensaje de 60 hoy.");
    expect(cuotaTexto({ usados: 60, limite: 60, restantes: 0, reinicia_en: "" })).toMatch(/Usaste los 60 mensajes/);
    expect(cuotaTexto({ usados: 5, limite: null, restantes: null, reinicia_en: "" })).toBe("");
    expect(cuotaTexto(null)).toBe("");
  });

  it("todos los tipos de respuesta tienen etiqueta", () => {
    for (const t of ["pregunta", "explicacion", "plan_accion", "orientacion", "fuera_de_alcance", "bloqueado"] as const) {
      expect(TIPO_RESPUESTA[t].etiqueta).toBeTruthy();
    }
  });

  it("separa párrafos sin interpretar HTML", () => {
    expect(parrafos("uno\n\n\ndos <b>x</b>\n\n")).toEqual(["uno", "dos <b>x</b>"]);
  });

  it("muestra la hora en Chile", () => {
    expect(horaCorta("2026-10-28T22:05:00")).toBe("19:05");
    expect(horaCorta(null)).toBe("");
  });
});

describe("HU-15 · conversación", () => {
  it("sugiere preguntas con las brechas REALES del contexto, empezando por la prioritaria", () => {
    const s = sugerenciasIniciales(contexto());
    expect(s[0]).toMatch(/cerrar primero/);
    expect(s.some((q) => q.includes("DAT-001"))).toBe(true);
    expect(s.some((q) => q.includes("GOB-002"))).toBe(false);
    const conFoco = sugerenciasIniciales(contexto({ foco: { ruta_id: 1, nombre: "Privacidad - Inicial", nivel: "Inicial" } }));
    expect(conFoco.at(-1)).toMatch(/Privacidad - Inicial/);
    expect(sugerenciasIniciales(contexto({ brechas: [] }))).toHaveLength(1);
    expect(sugerenciasIniciales(null)).toEqual([]);
  });

  it("retoma la conversación activa del mismo módulo, nunca una de solo lectura", () => {
    const items = [conv({ id: 3, estado: "solo_lectura" }), conv({ id: 2, ruta_id: 5 }), conv({ id: 1 })];
    expect(conversacionParaRetomar(items, null)?.id).toBe(1);
    expect(conversacionParaRetomar(items, 5)?.id).toBe(2);
    expect(conversacionParaRetomar(items, 9)).toBeNull();
  });

  it("el mensaje provisional del usuario tiene id negativo (no choca con los guardados)", () => {
    const m = mensajeProvisional("hola", "Avanzado");
    expect(m.id).toBeLessThan(0);
    expect(m).toMatchObject({ rol: "usuario", tipo: "pregunta", nivel: "Avanzado", contenido: "hola" });
  });

  it("traduce los errores del backend", () => {
    const e = (status: number, codigo: string, mensaje = "") => new ErrorBff(status, { codigo, mensaje });
    expect(mensajeTutor(e(403, "CONTRATO_NO_VIGENTE"))).toMatch(/no está activo/);
    expect(mensajeTutor(e(429, "CUOTA_TUTOR_AGOTADA", "Tu empresa usó los 60 mensajes"))).toBe("Tu empresa usó los 60 mensajes");
    expect(mensajeTutor(e(409, "CONVERSACION_DESACTUALIZADA"))).toMatch(/evaluación más reciente/);
    expect(mensajeTutor(e(503, "TUTOR_NO_DISPONIBLE"))).toMatch(/no se perdió/);
    expect(mensajeTutor(new Error("x"))).toMatch(/No pudimos/);
    expect(tutorSinServicio(e(403, "NO_AUTORIZADO"))).toBe(true);
    expect(tutorSinServicio(e(503, "TUTOR_NO_DISPONIBLE"))).toBe(false);
  });
});

describe("HU-15 v1.1 · seguimiento de pasos", () => {
  it("'Explícame este paso' pide detalle de ese paso, en primera persona", () => {
    const q = preguntaPaso({ orden: 2, accion: "Bloquear las herramientas no autorizadas" });
    expect(q).toMatch(/^Explícame en detalle cómo hago el paso 2: «Bloquear las herramientas no autorizadas»/);
  });
});

describe("HU-15 · BFF del cliente", () => {
  it("reenvía solo las rutas del tutor con su método", () => {
    expect(autorizarRutaCliente("GET", ["tutor", "contexto"]).ok).toBe(true);
    expect(autorizarRutaCliente("GET", ["tutor", "conversaciones"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["tutor", "conversaciones"]).ok).toBe(true);
    expect(autorizarRutaCliente("GET", ["tutor", "conversaciones", "4"]).ok).toBe(true);
    expect(autorizarRutaCliente("PATCH", ["tutor", "conversaciones", "4"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["tutor", "conversaciones", "4"]).ok).toBe(true);
    const msg = autorizarRutaCliente("POST", ["tutor", "conversaciones", "4", "mensajes"]);
    expect(msg.ok && msg.timeoutMs).toBe(60_000);
    // Lo demás no pasa
    expect(autorizarRutaCliente("DELETE", ["tutor", "conversaciones"]).ok).toBe(false);
    expect(autorizarRutaCliente("PATCH", ["tutor", "conversaciones", "4", "mensajes"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["tutor", "conversaciones", "x"]).ok).toBe(false);
    expect(autorizarRutaCliente("DELETE", ["formacion", "avance"]).ok).toBe(false);
    expect(autorizarRutaCliente("PATCH", ["evaluaciones", "1"]).ok).toBe(false);
  });
});
