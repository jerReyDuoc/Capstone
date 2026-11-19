/**
 * Asistente de registro como guía: lista blanca del proxy, conversación guardada en el navegador y la
 * revisión simple del registro (agrupar alertas y elegir el paso siguiente).
 */
import { describe, expect, it } from "vitest";
import {
  agruparRevision, claveConversacion, cuotaTexto, guardarConversacion, historialParaEnviar, leerConversacion, pasoSiguiente,
  preguntaAlerta, validarPregunta, type AlertaRegistro, type MensajeGuia,
} from "@/lib/guiaRegistro";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";
import { borrarClavesConPrefijo, PREFIJOS_DE_CUENTA } from "@/lib/sesionNavegador";

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
    guardarConversacion(almacen, 7, [{ id: "1", rol: "usuario", texto: "hola" }]);
    expect(leerConversacion(almacen, 7)).toEqual([{ id: "1", rol: "usuario", texto: "hola" }]);
    datos.set(claveConversacion(7), JSON.stringify([{ rol: "admin", texto: 1 }, { id: "2", rol: "guia", texto: "ok" }]));
    expect(leerConversacion(almacen, 7).map((m) => m.id)).toEqual(["2"]);
    datos.set(claveConversacion(7), "{no es json");
    expect(leerConversacion(almacen, 7)).toEqual([]);
    guardarConversacion(almacen, 7, []);
    expect(datos.size).toBe(0);
  });

  it("Corrección 18-11: la conversación es de una cuenta y no la ve otra", () => {
    const datos = new Map<string, string>();
    const almacen = {
      getItem: (k: string) => datos.get(k) ?? null,
      setItem: (k: string, v: string) => void datos.set(k, v),
      removeItem: (k: string) => void datos.delete(k),
    };
    guardarConversacion(almacen, 1, [{ id: "a", rol: "usuario", texto: "de la cuenta 1" }]);
    expect(leerConversacion(almacen, 2)).toEqual([]);
    expect(leerConversacion(almacen, 1)).toHaveLength(1);
    // Sin usuario conocido no se lee ni se guarda nada
    expect(leerConversacion(almacen, null)).toEqual([]);
    guardarConversacion(almacen, null, [{ id: "b", rol: "usuario", texto: "x" }]);
    expect([...datos.keys()]).toEqual([claveConversacion(1)]);
    // La clave de antes (sin dueño) se descarta y nunca se muestra
    datos.set("guia-registro:conversacion", JSON.stringify([{ id: "v", rol: "usuario", texto: "vieja" }]));
    expect(leerConversacion(almacen, 2)).toEqual([]);
    expect(datos.has("guia-registro:conversacion")).toBe(false);
  });

  it("Corrección 18-11: al cerrar sesión se borra lo de la cuenta y nada más", () => {
    const datos = new Map<string, string>([
      [claveConversacion(1), "[]"], [claveConversacion(2), "[]"], ["guia-registro:conversacion", "[]"],
      ["mapa-datos:guia-plegada", "1"],
    ]);
    const almacen = {
      get length() { return datos.size; },
      key: (i: number) => [...datos.keys()][i] ?? null,
      removeItem: (k: string) => void datos.delete(k),
    };
    expect(borrarClavesConPrefijo(almacen, PREFIJOS_DE_CUENTA)).toBe(3);
    expect([...datos.keys()]).toEqual(["mapa-datos:guia-plegada"]);
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
