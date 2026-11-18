/** Auditoría UX 16-11 · Fase 6: ningún mensaje para el cliente lleva jerga técnica. */
import { describe, expect, it } from "vitest";
import {
  MENSAJE_EVIDENCIA_BLOQUEADA,
  mensajeEvidencia,
  mensajePorEstado,
  textoSeguro,
  tieneJerga,
} from "@/lib/mensajesUsuario";

describe("mensajes en lenguaje de usuario", () => {
  it("el bloqueo preventivo se explica sin LLM ni prompt injection", () => {
    const m = mensajeEvidencia("Bloqueo preventivo: posible prompt injection en la evidencia. La evidencia no fue enviada al LLM");
    expect(m).toBe(MENSAJE_EVIDENCIA_BLOQUEADA);
    expect(m).toBe("No pudimos analizar este archivo. Revisa que no contenga instrucciones o texto inusual y súbelo de nuevo.");
    expect(m).not.toMatch(/LLM|prompt|injection/i);
  });

  it("los textos técnicos se reemplazan por el respaldo; los claros pasan tal cual", () => {
    expect(textoSeguro("Error 502 al consultar /api/evaluaciones/1", "Respaldo")).toBe("Respaldo");
    expect(textoSeguro("Usuario de empresa cliente (id 2)", "Respaldo")).toBe("Respaldo");
    expect(textoSeguro("ValueError: token inválido", "Respaldo")).toBe("Respaldo");
    expect(textoSeguro("La evidencia no demuestra un avance.", "Respaldo")).toBe("La evidencia no demuestra un avance.");
    expect(textoSeguro("", "Respaldo")).toBe("Respaldo");
  });

  it("los estados HTTP tienen un mensaje claro", () => {
    for (const s of [0, 401, 403, 404, 409, 429, 500, 502, 503, 504, 418]) {
      const m = mensajePorEstado(s);
      expect(tieneJerga(m)).toBe(false);
      expect(m).not.toMatch(/HTTP|\d{3}/);
    }
  });
});
