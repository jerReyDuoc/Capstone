/**
 * Bandeja de revisión: textos de los eventos que nacen al verificar la respuesta de la IA
 * (datos sin respaldo, información que no debía mostrarse, instrucciones del documento).
 */
import { describe, expect, it } from "vitest";
import {
  describirHallazgo,
  NOMBRE_ORIGEN_EVENTO,
  NOMBRE_RESOLUCION,
  nombreTipoEvento,
  ORIGEN_SALIDA_IA,
  TEXTO_MOTIVO,
  textosEvento,
} from "@/lib/admin/revision";
import { motivoEvidencia } from "@/lib/cuestionario/modelo";

describe("eventos de la verificación de la respuesta de la IA", () => {
  it("tiene un origen con nombre legible", () => {
    expect(NOMBRE_ORIGEN_EVENTO[ORIGEN_SALIDA_IA]).toBe("Respuesta de la IA retenida por la verificación");
  });

  it("nombra los tipos de evento sin guiones bajos", () => {
    expect(nombreTipoEvento("alucinacion")).toBe("Datos sin respaldo");
    expect(nombreTipoEvento("fuga_contexto")).toBe("Información que no debía mostrarse");
    expect(nombreTipoEvento("prompt_injection")).toBe("Intento de manipulación");
    expect(nombreTipoEvento("tipo_nuevo")).toBe("tipo nuevo");
    expect(nombreTipoEvento(null)).toBe("evento");
  });

  it("describe el hallazgo a partir de la regla", () => {
    expect(describirHallazgo("salida.alucinacion.cita_inexistente")).toBe(
      "Citó entre comillas un texto que no está en el documento.",
    );
    expect(describirHallazgo("salida.fuga.datos_personales")).toContain("RUT");
    expect(describirHallazgo("manipulacion.aprueba")).toBeNull();
    expect(describirHallazgo(null)).toBeNull();
  });

  it("cambia los textos del detalle según el origen", () => {
    const ia = textosEvento({ origen: ORIGEN_SALIDA_IA });
    expect(ia.titulo).toBe("La respuesta de la IA no pasó la verificación");
    expect(ia.pregunta).toBe("¿La verificación acertó?");
    expect(ia.nombreOpcion.ataque_confirmado).toBe("Problema confirmado");
    const ataque = textosEvento({ origen: "evidencia" });
    expect(ataque.titulo).toBe("Posible intento de manipular a la IA");
    expect(ataque.nombreOpcion).toEqual(NOMBRE_RESOLUCION);
  });

  it("no muestra códigos internos de historias ni tareas", () => {
    const textos = [
      ...Object.values(NOMBRE_ORIGEN_EVENTO),
      ...Object.values(textosEvento({ origen: ORIGEN_SALIDA_IA })).flatMap((v) => (typeof v === "string" ? [v] : Object.values(v))),
      TEXTO_MOTIVO.seguridad.ayuda,
    ];
    for (const t of textos) expect(t).not.toMatch(/\b(HU|T)-\d+/);
  });
});

describe("motivo de una evidencia sin resultado de la IA", () => {
  const base = { estado_validacion: "rejected", clasificacion_llm: null };

  it("muestra el aviso de la revisión automática", () => {
    const aviso = "El análisis automático incluyó datos que no aparecen en tu documento. Quedó pendiente de revisión.";
    expect(motivoEvidencia({ ...base, errores_validacion: [aviso] })).toBe(aviso);
  });

  it("traduce el bloqueo de seguridad a palabras simples", () => {
    const m = motivoEvidencia({ ...base, errores_validacion: ["Bloqueo preventivo: posible prompt injection en la evidencia."] });
    expect(m).toContain("instrucciones a la IA");
    expect(m).not.toMatch(/prompt injection|LLM/i);
  });

  it("no muestra nada si la IA clasificó o si no hay motivo", () => {
    expect(motivoEvidencia({ estado_validacion: "rejected", clasificacion_llm: "cumplido", errores_validacion: ["x"] })).toBeNull();
    expect(motivoEvidencia({ estado_validacion: "validated", clasificacion_llm: null, errores_validacion: ["x"] })).toBeNull();
    expect(motivoEvidencia({ ...base, errores_validacion: [] })).toBeNull();
    expect(motivoEvidencia({ ...base, errores_validacion: null })).toBeNull();
  });
});
