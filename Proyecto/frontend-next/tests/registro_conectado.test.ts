/**
 * El registro de actividades conectado con el resto del cumplimiento: nivel de riesgo de cada actividad,
 * ruta de remediación de las brechas del registro, la evaluación de impacto y el aviso de privacidad que
 * toman el registro, el dato opcional de volumen y la lista blanca del proxy.
 */
import { describe, expect, it } from "vitest";
import {
  actividadesPiaIniciales, advertenciasVisibles, generarBorrador, MAX_ACTIVIDADES_PIA, textoRegistroBorrador,
  type CatalogoBorradoresApi,
} from "@/lib/borradores";
import {
  cambiosContenido, contenidoVacio, hrefCorregirBrecha, PASO_DE_CLAVE, rutaRemediacion, textoEstadoRegistro,
  textoRiesgo, TONO_RIESGO, type BrechaRegistro, type RiesgoActividad,
} from "@/lib/registroActividades";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";

const CODIGO_INTERNO = /\b(?:HU|T)-\d{2}\b|\b(?:ERR-)?(?:DAT|GOB|RIE|SEG)-\d{3}\b/;

function riesgo(extra: Partial<RiesgoActividad> = {}): RiesgoActividad {
  return { nivel: "Alto", puntaje: 12, probabilidad: 3, impacto: 4, requiere_pia: true, motivos_pia: ["Su riesgo inherente es alto."],
    mayor_riesgo: true, ...extra };
}

function brecha(extra: Partial<BrechaRegistro> = {}): BrechaRegistro {
  return {
    codigo: "sin_plazo", titulo: "Datos sin plazo de conservación", texto: "«Pagos»: falta el plazo de: Salud.",
    severidad: "Media", paso: 5, actividad: { id: 7, nombre: "Pagos" }, flujo_id: null, obligacion: "Mantener el registro",
    ruta: { id: 3, nombre: "Privacidad desde el diseño", nivel: "Inicial", horas: 4, estado: "en_curso" },
    remediacion: { evaluacion_id: 21, respuesta_id: 99, estado: "no_cumplido", estado_nombre: "No cumplido", abierta: true },
    ...extra,
  };
}

describe("nivel de riesgo de una actividad", () => {
  it("dice el nivel y si se recomienda una evaluación de impacto", () => {
    expect(textoRiesgo(riesgo())).toBe("Riesgo alto · evaluación de impacto recomendada");
    expect(textoRiesgo(riesgo({ nivel: "Bajo", requiere_pia: false }))).toBe("Riesgo bajo");
    expect(textoRiesgo(null)).toMatch(/sin calcular/);
    expect(Object.keys(TONO_RIESGO)).toEqual(["Bajo", "Medio", "Alto", "Crítico"]);
  });
});

describe("brechas del registro y su ruta de remediación", () => {
  it("corrige la actividad en su paso, sigue con el módulo y termina re-evaluando el control", () => {
    const pasos = rutaRemediacion(brecha());
    expect(pasos.map((p) => p.clave)).toEqual(["corregir", "formacion", "remediacion"]);
    expect(pasos[0].href).toBe("/empresa/registro-actividades?actividad=7&paso=5");
    expect(pasos[1].href).toBe("/panel/capacitacion/3?evaluacion=21");
    expect(pasos[1].texto).toContain("en curso");
    expect(pasos[2].href).toBe("/panel/remediacion?evaluacion=21&control=99");
    for (const p of pasos) expect(p.texto).not.toMatch(CODIGO_INTERNO);
  });

  it("las transferencias se corrigen en el mapa y un módulo completado queda marcado", () => {
    expect(hrefCorregirBrecha(brecha({ codigo: "transferencia_sin_garantia", paso: 4 })).href).toBe("/empresa/mapa-datos");
    expect(hrefCorregirBrecha(brecha({ codigo: "flujo_sin_actividad", actividad: null, paso: null })).href)
      .toBe("/empresa/registro-actividades");
    const hecha = rutaRemediacion(brecha({ ruta: { id: 3, nombre: "M", nivel: null, horas: null, estado: "completado" } }));
    expect(hecha.find((p) => p.clave === "formacion")?.hecho).toBe(true);
    // si el control ya no tiene brecha o no hay módulo, la ruta es más corta
    expect(rutaRemediacion(brecha({ ruta: null, remediacion: null })).map((p) => p.clave)).toEqual(["corregir"]);
  });

  it("resume el estado del mapa y del registro", () => {
    const base = { mapa: { iniciado: true, version: 3, elementos: 4, flujos: 2, flujos_sin_actividad: 0 },
      registro: { activas: 3, vigentes: 1, completas: 2, en_revision: 1, borradores: 1, por_revisar: 0, completitud: 80,
        vigente_completo: false, faltantes: [] } };
    expect(textoEstadoRegistro(base)).toBe("1 de 3 actividades vigentes · 80 % completo");
    expect(textoEstadoRegistro({ ...base, registro: { ...base.registro, vigente_completo: true } })).toMatch(/vigente y completo/);
    expect(textoEstadoRegistro({ ...base, mapa: { ...base.mapa, iniciado: false } })).toMatch(/mapa de datos/);
    expect(textoEstadoRegistro({ ...base, registro: { ...base.registro, activas: 0 } })).toMatch(/registra tus actividades/);
  });
});

describe("borradores que toman el registro", () => {
  const registro: CatalogoBorradoresApi["registro"] = {
    actividades: [
      { actividad_id: 1, nombre: "Atención con IA", nivel: "Crítico", puntaje: 20, requiere_pia: true, motivos_pia: ["x"], vigente: true },
      { actividad_id: 2, nombre: "Pagos", nivel: "Bajo", puntaje: 3, requiere_pia: false, motivos_pia: [], vigente: true },
    ],
    pia: [{ actividad_id: 1, nombre: "Atención con IA", nivel: "Crítico", puntaje: 20, requiere_pia: true, motivos_pia: ["x"], vigente: true }],
    finalidades: 3,
  };

  it("la evaluación de impacto parte con las actividades recomendadas o con la que se pidió", () => {
    expect(actividadesPiaIniciales(registro, null)).toEqual([1]);
    expect(actividadesPiaIniciales(registro, 2)).toEqual([2]);
    expect(actividadesPiaIniciales(registro, 999)).toEqual([1]);       // una ajena no se acepta
    expect(actividadesPiaIniciales(undefined, 2)).toEqual([]);
  });

  it("explica qué tomará cada plantilla del registro", () => {
    expect(textoRegistroBorrador("politica_llm", registro, 0)).toBeNull();
    expect(textoRegistroBorrador("aviso_privacidad", registro, 0)).toMatch(/3 finalidades/);
    expect(textoRegistroBorrador("pia", registro, 1)).toMatch(/1 actividad/);
    expect(textoRegistroBorrador("pia", registro, 0)).toMatch(/Ninguna actividad/);
    expect(textoRegistroBorrador("pia", { actividades: [], pia: [], finalidades: 0 }, 0)).toMatch(/vacío/);
  });

  it("las advertencias del registro tienen texto para la persona", () => {
    const t = advertenciasVisibles(["registro_aplicado", "registro_no_vigente", "registro_vacio", "pia_sin_alto_riesgo"]);
    expect(t).toHaveLength(4);
    for (const x of t) expect(x).not.toMatch(CODIGO_INTERNO);
  });

  it("solo la evaluación de impacto envía actividades y como máximo diez", async () => {
    const enviados: unknown[] = [];
    const original = globalThis.fetch;
    globalThis.fetch = (async (_u: string, init: RequestInit) => {
      enviados.push(JSON.parse(String(init.body)));
      return new Response(JSON.stringify({ borrador: {}, cuota: {} }), { status: 201, headers: { "Content-Type": "application/json" } });
    }) as typeof fetch;
    try {
      await generarBorrador("pia", "", false, Array.from({ length: 14 }, (_, i) => i + 1));
      await generarBorrador("aviso_privacidad", "", false, [1, 2]);
    } finally {
      globalThis.fetch = original;
    }
    expect((enviados[0] as { actividades: number[] }).actividades).toHaveLength(MAX_ACTIVIDADES_PIA);
    expect(enviados[1]).not.toHaveProperty("actividades");
  });
});

describe("volumen de personas (dato opcional de la actividad)", () => {
  it("se completa en el paso 2 y solo se envía si cambió", () => {
    expect(PASO_DE_CLAVE.volumen).toBe(2);
    const guardado = contenidoVacio("Pagos");
    expect(cambiosContenido(guardado, { ...guardado, volumen: null })).toEqual({});
    expect(cambiosContenido(guardado, { ...guardado, volumen: "mas_100_mil" })).toEqual({ volumen: "mas_100_mil" });
    expect(cambiosContenido({ ...guardado, volumen: "hasta_mil" }, { ...guardado, volumen: null })).toEqual({ volumen: null });
  });
});

describe("proxy del cliente", () => {
  it("deja pasar el estado del registro y su uso como evidencia, nada más", () => {
    expect(autorizarRutaCliente("GET", ["registro-actividades", "cumplimiento"]).ok).toBe(true);
    expect(autorizarRutaCliente("POST", ["registro-actividades", "cumplimiento", "evidencia"]).ok).toBe(true);
    expect(autorizarRutaCliente("DELETE", ["registro-actividades", "cumplimiento"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["registro-actividades", "cumplimiento"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["registro-actividades", "cumplimiento", "evidencia"]).ok).toBe(false);
  });
});
