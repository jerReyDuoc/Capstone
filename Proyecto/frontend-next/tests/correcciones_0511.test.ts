/**
 * Correcciones 05-11 · lógica pura de las mejoras de interfaz.
 */
import { describe, expect, it } from "vitest";
import { rutMientrasEscribe, rutValido } from "@/lib/admin/api";
import { errorRubro, notaVisible } from "@/lib/admin/rubros";
import { fechaChile, fechaDelServidor, fechaHoraChile } from "@/lib/fechas";
import { avancePorDimension, recortar } from "@/lib/remediacion";
import { autorizarRutaAdmin } from "@/lib/servidor/proxyAdmin";
import { esCharla, nombreBrecha, subtituloTutor } from "@/lib/tutor";

describe("RUT con puntos y guion automáticos", () => {
  it("formatea mientras se escribe y queda válido", () => {
    expect(rutMientrasEscribe("7")).toBe("7");
    expect(rutMientrasEscribe("76")).toBe("7-6");
    expect(rutMientrasEscribe("760864285")).toBe("76.086.428-5");
    expect(rutMientrasEscribe("76.086.428-5")).toBe("76.086.428-5");
    expect(rutMientrasEscribe("12345678k")).toBe("12.345.678-K");
    expect(rutMientrasEscribe("76a.08b6")).toBe("7.608-6");
    expect(rutValido(rutMientrasEscribe("760864285"))).toBe(true);
  });
});

describe("fechas en hora de Chile", () => {
  it("una fecha-hora sin zona del backend es UTC", () => {
    expect(fechaDelServidor("2026-11-05T18:21:00")?.toISOString()).toBe("2026-11-05T18:21:00.000Z");
    // 18:21 UTC en noviembre (horario de verano, UTC-3) = 15:21 en Chile
    expect(fechaHoraChile("2026-11-05T18:21:00")).toBe("5 nov 2026, 15:21");
    expect(fechaHoraChile("2026-11-05T18:21:00+00:00")).toBe("5 nov 2026, 15:21");
  });

  it("una fecha sola no cambia de día y lo vacío es un guion", () => {
    expect(fechaChile("2026-11-05")).toBe("5 nov 2026");
    expect(fechaChile(null)).toBe("—");
    expect(fechaHoraChile("no es fecha")).toBe("—");
  });
});

describe("rubros del panel interno", () => {
  const existentes = [{ id: 1, nombre: "Retail" }];
  it("valida largo, letras y duplicados sin importar mayúsculas", () => {
    expect(errorRubro("1", existentes)).toMatch(/2 letras/);
    expect(errorRubro("  retail ", existentes)).toMatch(/Ya existe/);
    expect(errorRubro("Retail", existentes, 1)).toBeNull();
    expect(errorRubro("Minería", existentes)).toBeNull();
  });

  it("el BFF deja pasar solo las rutas de rubros previstas", () => {
    expect(autorizarRutaAdmin("GET", ["admin", "rubros"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "rubros"]).ok).toBe(true);
    expect(autorizarRutaAdmin("PATCH", ["admin", "rubros", "3"]).ok).toBe(true);
    expect(autorizarRutaAdmin("PATCH", ["admin", "rubros"]).ok).toBe(false);
  });

  it("oculta la nota de la versión sembrada", () => {
    expect(notaVisible("Versión inicial: matriz sembrada por las migraciones (HU-24).")).toBeNull();
    expect(notaVisible("Se agregan controles de la Ley 21.719")).toMatch(/Ley/);
  });
});

describe("Tu madurez ahora", () => {
  it("suma lo que subió cada dimensión y ordena primero donde más subió", () => {
    const dominios = [
      { nombre: "Gobernanza de IA", puntaje: 60, meta: 75 },
      { nombre: "Protección de Datos", puntaje: 40, meta: 75 },
    ];
    const evolucion = [
      { fecha: null, antes: 40, despues: 42.5, dominio: "Protección de Datos" },
      { fecha: null, antes: 42.5, despues: 44, dominio: "Protección de Datos" },
      { fecha: null, antes: 44, despues: 45, dominio: "Gobernanza de IA" },
    ];
    const r = avancePorDimension(dominios, evolucion, [{ dominio: "Gobernanza de IA" }]);
    expect(r.map((x) => [x.dominio, x.aporte, x.mejoradas, x.abiertas])).toEqual([
      ["Protección de Datos", 4, 2, 0],
      ["Gobernanza de IA", 1, 1, 1],
    ]);
    expect(recortar("a".repeat(100), 10)).toHaveLength(10);
  });
});

describe("Tutor sin códigos internos", () => {
  it("nombra la brecha por su descripción", () => {
    expect(nombreBrecha("No existe una política de uso de IA.")).toBe("No existe una política de uso de IA.");
    expect(nombreBrecha("")).toBe("Brecha de tu evaluación");
    expect(nombreBrecha("x".repeat(200)).length).toBeLessThanOrEqual(90);
  });
});

describe("Tutor · encabezado y charla simple", () => {
  it("sin número interno de evaluación ni 'tus 0 brechas'", () => {
    expect(subtituloTutor(3, "28 de octubre de 2026")).toBe("Tus 3 brechas de la evaluación del 28 de octubre de 2026");
    expect(subtituloTutor(1, null)).toBe("Tu brecha de tu evaluación más reciente");
    expect(subtituloTutor(0, "28 de octubre de 2026")).toBe("Tu evaluación del 28 de octubre de 2026 no tiene brechas abiertas");
  });

  it("un saludo o despedida no lleva etiqueta de tipo", () => {
    expect(esCharla({ tipo: "orientacion", pasos: [], brechas: [] })).toBe(true);
    expect(esCharla({ tipo: "explicacion", pasos: [], brechas: [] })).toBe(false);
  });
});
