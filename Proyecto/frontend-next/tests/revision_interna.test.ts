/**
 * Revisión interna del registro (lib/revisionInterna.ts) y la lista blanca del proxy para sus rutas.
 */
import { describe, expect, it } from "vitest";
import {
  accionesPunto, enlaceCorregir, fechaCorta, filtrarObjetos, normalizar, ordenarObservaciones, problemaNombre,
  textoPeriodicidad, verificablesDeUnaVez, type ObjetoRevision, type Observacion, type Periodicidad, type Punto,
} from "@/lib/revisionInterna";
import { autorizarRutaCliente, TIPOS_PAQUETE_REVISION } from "@/lib/servidor/proxyCliente";

const punto = (p: Partial<Punto>): Punto => ({
  codigo: "plazos", titulo: "Plazos", resultado: "cumple", detalle: "", bloqueante: false, revision: "pendiente",
  nota: null, fecha_revision: null, ...p,
});

const objeto = (o: Partial<ObjetoRevision>): ObjetoRevision => ({
  clave: "actividad:1", tipo: "actividad", id: 1, nombre: "Pago de remuneraciones", subtitulo: "Versión N.º 1", huella: "h",
  items: [], revisados: 0, por_revisar: 0, completo: false, fallas: 0, advertencias: 0, bloqueos: 0, ...o,
});

describe("acciones de cada punto (mismas reglas que el servidor)", () => {
  it("una falla no se verifica: se corrige o se acepta, salvo que sea bloqueante", () => {
    expect(accionesPunto(punto({ resultado: "falla" }))).toEqual({ verificar: false, aceptar: true, deshacer: false });
    expect(accionesPunto(punto({ resultado: "falla", bloqueante: true }))).toEqual({ verificar: false, aceptar: false, deshacer: false });
  });
  it("lo que cumple se verifica; la advertencia se verifica o se acepta; lo decidido se deshace", () => {
    expect(accionesPunto(punto({}))).toEqual({ verificar: true, aceptar: false, deshacer: false });
    expect(accionesPunto(punto({ resultado: "advertencia" }))).toEqual({ verificar: true, aceptar: true, deshacer: false });
    expect(accionesPunto(punto({ revision: "verificado" }))).toEqual({ verificar: false, aceptar: false, deshacer: true });
    expect(accionesPunto(punto({ resultado: "no_aplica", revision: "no_aplica" }))).toEqual({ verificar: false, aceptar: false, deshacer: false });
  });
  it("cuenta lo que se puede verificar de una vez (incluye lo desactualizado, no las fallas)", () => {
    const o = objeto({ items: [punto({}), punto({ codigo: "a", revision: "desactualizado" }), punto({ codigo: "b", resultado: "falla" }),
      punto({ codigo: "c", revision: "verificado" }), punto({ codigo: "d", resultado: "no_aplica", revision: "no_aplica" })] });
    expect(verificablesDeUnaVez(o)).toBe(2);
  });
});

describe("filtros de la lista", () => {
  const lista = [
    objeto({ clave: "actividad:1", fallas: 1 }),
    objeto({ clave: "elemento:2", tipo: "elemento", nombre: "Sistema de Remuneraciones", completo: true }),
    objeto({ clave: "flujo:3", tipo: "flujo", nombre: "ERP → Banco" }),
  ];
  it("por tipo, avance y nombre sin tildes", () => {
    expect(filtrarObjetos(lista, "elemento", "todos", "").map((o) => o.clave)).toEqual(["elemento:2"]);
    expect(filtrarObjetos(lista, "todos", "pendientes", "").map((o) => o.clave)).toEqual(["actividad:1", "flujo:3"]);
    expect(filtrarObjetos(lista, "todos", "con_fallas", "").map((o) => o.clave)).toEqual(["actividad:1"]);
    expect(filtrarObjetos(lista, "todos", "todos", "remuneracion").length).toBe(2);
    expect(normalizar("  Sesión ÁREA ")).toBe("sesion area");
  });
});

describe("textos", () => {
  const base: Periodicidad = {
    estado: "al_dia", vence: "2027-11-13", dias: 200, base: "ultima_revision", plazo_meses: 12, aviso_dias: 30,
    recordatorio_correo: true, ultimo_recordatorio: null, personalizada: false, ultima_revision: null,
  };
  it("estado de la revisión periódica", () => {
    expect(textoPeriodicidad(base)).toMatchObject({ tono: "ok", titulo: "Revisión al día" });
    expect(textoPeriodicidad({ ...base, estado: "vencida", dias: -3 }).detalle).toMatch(/13-11-2027 \(3 día/);
    expect(textoPeriodicidad({ ...base, estado: "por_vencer", dias: 10 }).tono).toBe("aviso");
    expect(textoPeriodicidad({ ...base, estado: "sin_revision" }).titulo).toMatch(/primera revisión/);
    for (const e of ["al_dia", "por_vencer", "vencida", "sin_revision", "sin_registro"] as const) {
      expect(JSON.stringify(textoPeriodicidad({ ...base, estado: e }))).not.toMatch(/\b(HU|T)-\d{2}\b/);
    }
    expect(fechaCorta("2027-01-05T10:00:00")).toBe("05-01-2027");
  });
  it("dónde se corrige", () => {
    expect(enlaceCorregir({ tipo: "actividad", id: 4 }, "plazos").href).toBe("/empresa/registro-actividades?actividad=4&paso=5");
    expect(enlaceCorregir({ tipo: "actividad", id: 4 }, "transferencias").href).toBe("/empresa/mapa-datos");
    expect(enlaceCorregir({ tipo: "flujo", id: 9 }).href).toBe("/empresa/mapa-datos");
  });
  it("nombre de quien revisa", () => {
    expect(problemaNombre("Jason Sánchez")).toBeNull();
    expect(problemaNombre("")).toMatch(/Escribe/);
    expect(problemaNombre("ana@acme.cl")).toMatch(/solo letras/);
    expect(problemaNombre("J")).toMatch(/2 y 120/);
  });
  it("observaciones: primero las abiertas por prioridad", () => {
    const o = (n: number, estado: "abierta" | "cerrada", prioridad: "alta" | "media" | "baja", cierre: string | null = null) =>
      ({ numero: n, estado, prioridad, fecha_cierre: cierre }) as Observacion;
    const r = ordenarObservaciones([o(1, "cerrada", "alta", "2026-11-01"), o(2, "abierta", "baja"), o(3, "abierta", "alta"),
      o(4, "cerrada", "baja", "2026-11-10")]);
    expect(r.map((x) => x.numero)).toEqual([3, 2, 4, 1]);
  });
});

describe("proxy del cliente", () => {
  const ok = (m: string, r: string) => autorizarRutaCliente(m, r.split("/")).ok;
  it("deja pasar solo las rutas de la revisión interna", () => {
    expect(ok("GET", "registro-actividades/revision")).toBe(true);
    expect(ok("POST", "registro-actividades/revision/verificaciones")).toBe(true);
    expect(ok("POST", "registro-actividades/revision/observaciones/12/cerrar")).toBe(true);
    expect(ok("POST", "registro-actividades/revision/marcar")).toBe(true);
    expect(ok("PATCH", "registro-actividades/revision/configuracion")).toBe(true);
    expect(ok("DELETE", "registro-actividades/revision/observaciones/12")).toBe(false);
    expect(ok("PATCH", "registro-actividades/revision/marcar")).toBe(false);
  });
  it("el paquete es un ZIP binario y la verificación es una subida de archivo", () => {
    const zip = autorizarRutaCliente("GET", ["registro-actividades", "revision", "revisiones", "3", "paquete"]);
    expect(zip.ok && zip.binario && zip.tipos).toEqual(TIPOS_PAQUETE_REVISION);
    const pdf = autorizarRutaCliente("GET", ["registro-actividades", "revision", "revisiones", "3", "constancia"]);
    expect(pdf.ok && pdf.binario).toBe(true);
    const sub = autorizarRutaCliente("POST", ["registro-actividades", "revision", "paquetes", "verificacion"]);
    expect(sub.ok && sub.archivo).toBe(true);
  });
});
