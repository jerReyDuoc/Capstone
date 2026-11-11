/**
 * HU-25 · lógica pura de la pantalla "Retención de datos" y del proxy del panel interno.
 */
import { describe, expect, it } from "vitest";
import {
  describirPlazo, errorPlazo, etiquetaResultado, plazoLegible, requiereConfirmacion, resumenEjecucion, textoConfirmacion,
  type DetalleEjecucion, type RegistroLog,
} from "@/lib/admin/retencion";
import { autorizarRutaAdmin, filtrarQueryAdmin } from "@/lib/servidor/proxyAdmin";

const LIM = { min_dias: 30, max_dias: 3650 };

const detalle = (extra: Partial<DetalleEjecucion> = {}, conteos: Partial<DetalleEjecucion["conteos"]> = {}): DetalleEjecucion => ({
  origen: "cron",
  simulacion: false,
  inicio: "2026-11-10T03:00:00",
  duracion_ms: 1200,
  plazos_dias: { titulares: 365, arcop: null, eventos: null, tutor: 30 },
  fuente_plazo_titulares: "panel",
  fecha_corte_titulares: "2025-11-10",
  reglas_desactivadas: ["arcop", "eventos"],
  conteos: {
    titulares: 3, titulares_omitidos_por_arcop_abierta: 0, titulares_fallidos: 0,
    solicitudes_arcop: 0, eventos_seguridad: 0, conversaciones_tutor: 0, archivos_borrados: 2, ...conteos,
  },
  omitida_por_ejecucion_en_curso: false,
  error: null,
  ...extra,
});

const fila = (resultado: RegistroLog["resultado"], d: DetalleEjecucion): RegistroLog<DetalleEjecucion> => ({
  id: 1, fecha: "2026-11-10T03:00:01", actor_rol: "sistema", actor_id: null, resultado, detalle: d,
});

describe("plazo de retención", () => {
  it("valida el número de días dentro de los límites", () => {
    expect(errorPlazo("365", LIM)).toBeNull();
    expect(errorPlazo("30", LIM)).toBeNull();
    expect(errorPlazo("29", LIM)).toMatch(/entre 30 y 3650/);
    expect(errorPlazo("3651", LIM)).toMatch(/entre 30 y 3650/);
    expect(errorPlazo("", LIM)).toMatch(/número entero/);
    expect(errorPlazo("1e3", LIM)).toMatch(/número entero/);
    expect(errorPlazo("-5", LIM)).toMatch(/número entero/);
  });

  it("muestra plazos largos en años o meses", () => {
    expect(plazoLegible(365)).toBe("365 días (1 año)");
    expect(plazoLegible(730)).toBe("730 días (2 años)");
    expect(plazoLegible(90)).toBe("90 días (3 meses)");
    expect(plazoLegible(45)).toBe("45 días");
    expect(plazoLegible(null)).toBe("sin plazo");
  });

  it("describe el plazo vigente según su origen", () => {
    expect(describirPlazo({ modo: "plazo", plazo_titular_dias: 365, valor_entorno_dias: null })).toMatch(/fijado en este panel/);
    expect(describirPlazo({ modo: "entorno", plazo_titular_dias: 180, valor_entorno_dias: 180 })).toMatch(/valor por defecto/);
    expect(describirPlazo({ modo: "entorno", plazo_titular_dias: null, valor_entorno_dias: null })).toMatch(/no se anonimizan/);
    expect(describirPlazo({ modo: "desactivada", plazo_titular_dias: null, valor_entorno_dias: 365 })).toMatch(/^Desactivada/);
  });

  it("pide confirmar solo si el cambio adelanta la anonimización de alguien", () => {
    expect(requiereConfirmacion(365, 180, 4)).toBe(true);    // bajar con pendientes
    expect(requiereConfirmacion(null, 365, 2)).toBe(true);   // activar la regla
    expect(requiereConfirmacion(365, 180, 0)).toBe(false);   // bajar sin nadie afectado
    expect(requiereConfirmacion(180, 365, 10)).toBe(false);  // alargar
    expect(requiereConfirmacion(365, null, null)).toBe(false); // desactivar
    expect(requiereConfirmacion(365, 90, null)).toBe(true);  // sin vista previa: por si acaso
    expect(textoConfirmacion(1)).toMatch(/1 usuario temporal\./);
    expect(textoConfirmacion(null)).toMatch(/puede anonimizar/);
  });
});

describe("historial de ejecuciones", () => {
  it("etiqueta el resultado", () => {
    expect(etiquetaResultado(fila("ok", detalle())).texto).toBe("Completada");
    expect(etiquetaResultado(fila("ok", detalle({ simulacion: true }))).texto).toBe("Simulación");
    expect(etiquetaResultado(fila("omitido", detalle({ omitida_por_ejecucion_en_curso: true }))).tono).toBe("medio");
    expect(etiquetaResultado(fila("error", detalle({}, { titulares_fallidos: 2 }))).texto).toBe("Con 2 fallos");
    expect(etiquetaResultado(fila("error", detalle({ error: "ConnectionError" }))).texto).toBe("Falló");
  });

  it("resume con conteos y sin datos personales", () => {
    expect(resumenEjecucion(detalle())).toBe("3 usuarios temporales anonimizados");
    expect(resumenEjecucion(detalle({ simulacion: true }, { titulares: 1 }))).toBe("1 usuario temporal se anonimizaría");
    expect(resumenEjecucion(detalle({}, { titulares_omitidos_por_arcop_abierta: 1, titulares_fallidos: 1, conversaciones_tutor: 4 })))
      .toBe("3 usuarios temporales anonimizados · 1 en espera por ARCOP abierta · 1 con error · 4 registros de otras reglas");
    expect(resumenEjecucion(detalle({ omitida_por_ejecucion_en_curso: true }))).toMatch(/otra ejecución en curso/);
    expect(resumenEjecucion(null)).toBe("—");
  });
});

describe("proxy del panel interno", () => {
  it("permite solo las rutas de retención previstas", () => {
    expect(autorizarRutaAdmin("GET", ["admin", "retencion"]).ok).toBe(true);
    expect(autorizarRutaAdmin("PATCH", ["admin", "retencion"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["admin", "retencion", "vista-previa"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["admin", "retencion", "ejecuciones"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "retencion", "simulacion"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "retencion", "ejecuciones"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "retencion"]).ok).toBe(false);
    expect(autorizarRutaAdmin("PATCH", ["admin", "retencion", "ejecuciones"]).ok).toBe(false);
    expect(autorizarRutaAdmin("GET", ["admin", "retencion", "simulacion"]).ok).toBe(false);
  });

  it("deja pasar el plazo de la vista previa y descarta lo demás", () => {
    expect(filtrarQueryAdmin(new URLSearchParams("dias=365"))).toBe("?dias=365");
    expect(filtrarQueryAdmin(new URLSearchParams("dias=365;drop"))).toBe("");
    expect(filtrarQueryAdmin(new URLSearchParams("dias=123456"))).toBe("");
  });
});
