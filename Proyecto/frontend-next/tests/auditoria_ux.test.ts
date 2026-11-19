/** Auditoría UX 16-11 · lógica pura de las mejoras de interfaz. */
import { describe, expect, it } from "vitest";
import { haceTexto, horaConZonas } from "@/lib/fechas";
import { pasoPendiente, PASOS_REGISTRO } from "@/lib/flujoRegistro";
import { NIVELES } from "@/lib/madurez";
import { entradaActiva, grupoActivo, gruposNavegacion, MI_EMPRESA, RUTA_ARMA_REGISTRO } from "@/lib/navegacion";
import { PRIORIDAD_TEXTO } from "@/lib/planFormativo";
import { claseBadgeSeveridad, SEVERIDAD_FORMA, SEVERIDADES_PRINCIPALES } from "@/lib/severidad";
import { estadoRegistro, proximosPasos } from "@/lib/tableroEmpresa";

describe("navegación por tareas", () => {
  it("cuatro grupos con rótulos cortos y sin códigos internos", () => {
    const grupos = gruposNavegacion("cliente");
    expect(grupos.map((g) => g.titulo)).toEqual(["Diagnóstico", "Plan de acción", "Privacidad y registro", "Documentos"]);
    for (const g of grupos) {
      for (const e of g.entradas) {
        expect(e.etiqueta.length).toBeLessThanOrEqual(18);
        expect(e.etiqueta).not.toMatch(/\b(HU|T)-\d+/);
      }
    }
  });

  it("conserva TODAS las rutas existentes (cambia la organización, no las URL)", () => {
    const rutas = [MI_EMPRESA, ...gruposNavegacion("cliente").flatMap((g) => g.entradas)].flatMap((e) => [e.ruta, ...(e.tambien ?? [])]);
    for (const r of [
      "/empresa", "/empresa/evaluaciones", "/empresa/documentos", "/empresa/borradores", "/empresa/mapa-datos",
      "/empresa/registro-actividades", "/empresa/mis-derechos", "/panel", "/panel/dominios", "/panel/brechas",
      "/panel/sector", "/panel/capacitacion", "/panel/informe", "/panel/remediacion",
    ]) expect(rutas).toContain(r);
  });

  it("los Borradores pasan a Documentos", () => {
    const docs = gruposNavegacion("cliente").find((g) => g.id === "documentos")!;
    expect(docs.entradas.map((e) => e.ruta)).toContain("/empresa/borradores");
  });

  it("el encuestado no ve las entradas del servicio contratado", () => {
    const rutas = gruposNavegacion("encuestado").flatMap((g) => g.entradas.map((e) => e.ruta));
    expect(rutas).not.toContain("/panel/remediacion");
    expect(rutas).not.toContain("/empresa/borradores");
    expect(rutas).toContain("/panel/mis-derechos");
  });

  it("Corrección 18-11 (2): el mapa de datos y el registro de actividades son dos entradas del menú", () => {
    const grupos = gruposNavegacion("cliente");
    const entradas = grupos.flatMap((g) => g.entradas);
    const mapa = entradas.find((e) => e.ruta === "/empresa/mapa-datos")!;
    const registro = entradas.find((e) => e.ruta === "/empresa/registro-actividades")!;
    expect(entradaActiva(mapa, "/empresa/mapa-datos")).toBe(true);
    expect(entradaActiva(mapa, RUTA_ARMA_REGISTRO)).toBe(true);
    expect(entradaActiva(mapa, "/empresa/registro-actividades")).toBe(false);
    expect(entradaActiva(registro, "/empresa/registro-actividades/revision")).toBe(true);
    expect(entradaActiva(registro, "/empresa/mapa-datos")).toBe(false);
    expect(grupoActivo(grupos, "/panel/capacitacion/7")).toBe("plan");
    expect(grupoActivo(grupos, "/empresa")).toBeNull();
  });

  it("Corrección 18-11 (2): el asistente no tiene entrada propia (se abre con su botón en las dos vistas)", () => {
    const rutas = gruposNavegacion("cliente").flatMap((g) => g.entradas).map((e) => e.ruta);
    expect(rutas).not.toContain("/empresa/asistente");
    expect(gruposNavegacion("encuestado").flatMap((g) => g.entradas).map((e) => e.ruta)).not.toContain("/empresa/mapa-datos");
  });
});

describe("flujo único del registro", () => {
  it("lleva al paso pendiente", () => {
    expect(pasoPendiente({ mapaIniciado: false, elementos: 0, actividades: 0 })).toBe(1);
    expect(pasoPendiente({ mapaIniciado: true, elementos: 4, actividades: 0 })).toBe(2);
    expect(pasoPendiente({ mapaIniciado: true, elementos: 4, actividades: 2 })).toBe(3);
  });
  it("tiene tres pasos", () => {
    expect(PASOS_REGISTRO).toHaveLength(3);
  });
});

describe("Mi empresa como tablero", () => {
  it("ordena lo accionable por urgencia", () => {
    const pasos = proximosPasos({
      diasContrato: 40,
      revision: { estado: "vencida", dias: -3 },
      porRevisar: 2,
      brechasCriticas: 3,
      registro: { mapaIniciado: false, activas: 0, vigenteCompleto: false, evidenciaAplicable: false },
    });
    expect(pasos[0].tono).toBe("urgente");
    expect(pasos.map((p) => p.id)).toEqual(expect.arrayContaining(["contrato", "revision", "propuestas", "criticas", "registro"]));
    expect(pasos.find((p) => p.id === "criticas")!.titulo).toBe("3 brechas críticas abiertas");
  });
  it("estado real del registro", () => {
    expect(estadoRegistro({ mapaIniciado: false, activas: 0, vigenteCompleto: false, evidenciaAplicable: false }).titulo).toMatch(/sin empezar/);
    expect(estadoRegistro({ mapaIniciado: true, activas: 3, vigenteCompleto: false, evidenciaAplicable: false }).titulo).toBe(
      "El registro aún no respalda controles",
    );
  });
  it("sin datos no inventa pasos", () => {
    expect(proximosPasos({ diasContrato: 300, revision: null, porRevisar: 0, brechasCriticas: 0, registro: null })).toEqual([]);
  });
});

describe("severidad: escala y vocabulario únicos", () => {
  it("cada severidad tiene forma propia (se distingue en escala de grises)", () => {
    const formas = SEVERIDADES_PRINCIPALES.map((s) => SEVERIDAD_FORMA[s]);
    expect(new Set(formas).size).toBe(4);
    expect(claseBadgeSeveridad("Baja")).toContain("sev-forma-baja");
  });
  it("Capacitación usa las mismas palabras que Brechas", () => {
    for (const s of SEVERIDADES_PRINCIPALES) expect(PRIORIDAD_TEXTO[s]).toBe(s);
    expect(Object.values(PRIORIDAD_TEXTO)).not.toContain("Urgente");
  });
  it("el verde (tono de marca/cumplido) solo se usa para el nivel más alto de madurez", () => {
    expect(NIVELES.gestionado.tono).not.toMatch(/ok|bajo/);
    expect(NIVELES.optimizado.tono).toBe("nivel-optimizado");
  });
});

describe("fechas", () => {
  const base = new Date("2026-11-17T12:00:00Z");
  it("Actualizado hace X", () => {
    expect(haceTexto(new Date(base.getTime() - 10_000), base)).toBe("hace un momento");
    expect(haceTexto(new Date(base.getTime() - 5 * 60_000), base)).toBe("hace 5 minutos");
    expect(haceTexto(new Date(base.getTime() - 60 * 60_000), base)).toBe("hace 1 hora");
  });
  it("hora con sus dos zonas", () => {
    // 03:00 UTC = 00:00 en Chile (verano, UTC-3)
    const corrida = new Date("2026-11-18T03:00:00Z");
    expect(horaConZonas(corrida, new Date("2026-11-17T22:00:00Z"))).toBe("mañana 00:00 (Chile) · 03:00 UTC");
    expect(horaConZonas(corrida, new Date("2026-11-18T03:30:00Z"))).toBe("hoy 00:00 (Chile) · 03:00 UTC");
  });
});
