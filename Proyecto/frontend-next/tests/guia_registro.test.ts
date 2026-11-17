/**
 * Asistente de registro como guía: lista blanca del proxy, conversación guardada en el navegador y la
 * revisión simple del registro (agrupar alertas y elegir el paso siguiente).
 */
import { describe, expect, it } from "vitest";
import {
  agruparRevision, cuotaTexto, guardarConversacion, historialParaEnviar, leerConversacion, pasoSiguiente,
  preguntaAlerta, validarPregunta, type AlertaRegistro, type MensajeGuia,
} from "@/lib/guiaRegistro";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";

const ok = (m: string, r: string) => autorizarRutaCliente(m, r.split("/")).ok;

const alerta = (p: Partial<AlertaRegistro>): AlertaRegistro => ({
  codigo: "actividad_sin_plazo", severidad: "Media", texto: "Falta el plazo", referencia: { tipo: "actividad", id: 3 }, ...p,
});

describe("proxy del cliente · asistente de registro", () => {
  it("deja pasar solo la guía (la entrevista y las propuestas ya no se usan)", () => {
    expect(ok("GET", "asistente/guia")).toBe(true);
    expect(ok("POST", "asistente/guia")).toBe(true);
    expect(ok("DELETE", "asistente/guia")).toBe(false);
    expect(ok("GET", "asistente")).toBe(false);
    expect(ok("POST", "asistente/sesiones")).toBe(false);
    expect(ok("POST", "asistente/propuestas/12/aceptar")).toBe(false);
  });

  it("preguntar tiene más tiempo (llama al servicio de IA)", () => {
    const r = autorizarRutaCliente("POST", ["asistente", "guia"]);
    expect(r.ok && r.timeoutMs).toBe(90_000);
  });
});

describe("conversación", () => {
  it("envía solo los últimos turnos, sin los bloqueados y recortados", () => {
    const ms: MensajeGuia[] = Array.from({ length: 10 }, (_, i) => ({
      id: String(i), rol: i % 2 ? "guia" : "usuario", texto: `m${i} ${"x".repeat(900)}`, bloqueado: i === 9,
    }));
    const h = historialParaEnviar(ms);
    expect(h).toHaveLength(6);
    expect(h.at(-1)?.texto.startsWith("m8")).toBe(true);
    expect(h.every((t) => t.texto.length <= 600)).toBe(true);
  });

  it("se guarda y se lee del almacenamiento, ignorando basura", () => {
    const datos = new Map<string, string>();
    const almacen = {
      getItem: (k: string) => datos.get(k) ?? null,
      setItem: (k: string, v: string) => void datos.set(k, v),
      removeItem: (k: string) => void datos.delete(k),
    };
    guardarConversacion(almacen, [{ id: "1", rol: "usuario", texto: "hola" }]);
    expect(leerConversacion(almacen)).toEqual([{ id: "1", rol: "usuario", texto: "hola" }]);
    datos.set("guia-registro:conversacion", JSON.stringify([{ rol: "admin", texto: 1 }, { id: "2", rol: "guia", texto: "ok" }]));
    expect(leerConversacion(almacen).map((m) => m.id)).toEqual(["2"]);
    datos.set("guia-registro:conversacion", "{no es json");
    expect(leerConversacion(almacen)).toEqual([]);
    guardarConversacion(almacen, []);
    expect(datos.size).toBe(0);
  });

  it("valida la pregunta y muestra la cuota en simple", () => {
    expect(validarPregunta("   ").ok).toBe(false);
    expect(validarPregunta("x".repeat(30), 20).ok).toBe(false);
    expect(validarPregunta("  ¿qué es un flujo? ")).toEqual({ ok: true, texto: "¿qué es un flujo?" });
    expect(cuotaTexto({ usados: 1, limite: 60, restantes: 59 })).toBe("Te quedan 59 preguntas hoy.");
    expect(cuotaTexto({ usados: 60, limite: 60, restantes: 0 })).toMatch(/Mañana/);
    expect(cuotaTexto(null, false)).toMatch(/guía básica/);
  });
});

describe("revisión de mi registro", () => {
  it("agrupa las alertas por tipo, con lo más grave primero", () => {
    const g = agruparRevision([
      alerta({}), alerta({ referencia: { tipo: "actividad", id: 4 } }),
      alerta({ codigo: "transferencia_sin_garantia", severidad: "Crítica", referencia: { tipo: "flujo", id: 9 } }),
    ]);
    expect(g.map((x) => [x.codigo, x.items.length])).toEqual([["transferencia_sin_garantia", 1], ["actividad_sin_plazo", 2]]);
    expect(g[0].vista).toBe("mapa");
    expect(g[1].queHacer).toMatch(/plazos/);
    expect(preguntaAlerta(g[1])).toContain("Falta cuánto tiempo se guardan los datos");
  });

  it("propone un solo paso según lo que ya existe", () => {
    const base = { revision: [] as AlertaRegistro[] };
    expect(pasoSiguiente({ ...base, mapa: { elementos: 0, flujos: 0, actividades: 0 } }).id).toBe("mapa");
    expect(pasoSiguiente({ ...base, mapa: { elementos: 3, flujos: 0, actividades: 0 } }).id).toBe("flujos");
    expect(pasoSiguiente({ ...base, mapa: { elementos: 3, flujos: 2, actividades: 0 } }).vista).toBe("registro");
    expect(pasoSiguiente({ revision: [alerta({})], mapa: { elementos: 3, flujos: 2, actividades: 1 } }).id).toBe("alertas");
    expect(pasoSiguiente({ ...base, mapa: { elementos: 3, flujos: 2, actividades: 1 } }).id).toBe("listo");
  });
});
