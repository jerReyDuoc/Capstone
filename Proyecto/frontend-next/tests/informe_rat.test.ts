/**
 * Informe del registro de actividades (lib/informeRat.ts), la lista blanca del proxy para sus rutas y
 * la guía para armar el mapa (lib/guiaMapa.ts).
 */
import { describe, expect, it } from "vitest";
import { pasosGuia, siguientePaso } from "@/lib/guiaMapa";
import { digitoVerificador, nivelDe, normalizarCodigo, problemaCodigo, textoAccionInforme, type ListaInformes } from "@/lib/informeRat";
import type { VistaMapa } from "@/lib/mapaDatos";
import { filtrarQuery } from "@/lib/servidor/proxy";
import { autorizarRutaCliente, TIPO_XLSX, TIPOS_DOCUMENTO } from "@/lib/servidor/proxyCliente";

describe("código verificable del informe", () => {
  it("usa el mismo dígito módulo 11 que el servidor", () => {
    // Mismos valores que app/application/informes/ficha.py (digito_verificador)
    expect(digitoVerificador(45)).toBe("0");
    expect(digitoVerificador(123)).toBe("6");
    expect(digitoVerificador(7)).toBe("8");
    expect(["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "K"]).toContain(digitoVerificador(999999));
  });

  it("normaliza y avisa antes de consultar", () => {
    expect(normalizarCodigo(" cia-reg-2026-000045-0 ")).toBe("CIA-REG-2026-000045-0");
    expect(problemaCodigo("CIA-REG-2026-000045-0")).toBeNull();
    expect(problemaCodigo("cia-reg-2026-000045-0")).toBeNull();
    expect(problemaCodigo("")).toMatch(/Escribe el código/);
    expect(problemaCodigo("CIA-2026-000045-0")).toMatch(/forma/);
    expect(problemaCodigo("CIA-REG-2026-000045-9")).toMatch(/último carácter/);
  });
});

describe("textos del informe", () => {
  it("nivel de cada celda de la matriz (probabilidad × impacto)", () => {
    expect([1, 4, 5, 9, 10, 14, 15, 25].map(nivelDe)).toEqual(["Bajo", "Bajo", "Medio", "Medio", "Alto", "Alto", "Crítico", "Crítico"]);
  });

  it("el botón dice qué va a pasar", () => {
    const base = { al_dia: false, ultima: null, previa: { puede_emitir: true, borrador: false } } as unknown as ListaInformes;
    expect(textoAccionInforme(base)).toBe("Generar informe oficial");
    expect(textoAccionInforme({ ...base, previa: { ...base.previa, borrador: true } })).toBe("Generar informe (borrador)");
    expect(textoAccionInforme({ ...base, al_dia: true, ultima: { id: 1 } as ListaInformes["ultima"] })).toBe("Descargar el informe al día");
    expect(textoAccionInforme({ ...base, previa: { ...base.previa, puede_emitir: false } })).toMatch(/al menos una actividad/);
  });
});

describe("proxy del cliente: informe del registro", () => {
  const ok = (metodo: string, ruta: string) => autorizarRutaCliente(metodo, ruta.split("/")).ok;

  it("deja pasar solo las rutas del informe", () => {
    expect(ok("GET", "registro-actividades/informes")).toBe(true);
    expect(ok("POST", "registro-actividades/informes")).toBe(true);
    expect(ok("GET", "registro-actividades/informes/verificacion")).toBe(true);
    expect(ok("POST", "registro-actividades/informes/12/enviar")).toBe(true);
    expect(ok("DELETE", "registro-actividades/informes/12")).toBe(false);
    expect(ok("POST", "registro-actividades/informes/12/descarga")).toBe(false);
  });

  it("la descarga es binaria y admite PDF o Excel", () => {
    const a = autorizarRutaCliente("GET", ["registro-actividades", "informes", "12", "descarga"]);
    expect(a.ok && a.binario).toBe(true);
    expect(a.ok && a.tipos).toEqual(["application/pdf", TIPO_XLSX]);
    // "Mis documentos" también descarga la planilla
    expect(TIPOS_DOCUMENTO).toContain(TIPO_XLSX);
  });

  it("pasa el código y el formato en la consulta", () => {
    expect(filtrarQuery(new URLSearchParams("codigo=CIA-REG-2026-000045-0&otro=x"))).toBe("?codigo=CIA-REG-2026-000045-0");
    expect(filtrarQuery(new URLSearchParams("formato=xlsx"))).toBe("?formato=xlsx");
  });
});

describe("guía para armar el mapa", () => {
  const vista = (extra: Partial<VistaMapa["resumen"]> = {}, otros: Partial<VistaMapa> = {}): VistaMapa => ({
    mapa: { version: 1, fecha_actualizacion: null, iniciado: true, plantilla_inicial: null },
    elementos: [], flujos: [], hallazgos: [],
    resumen: {
      sistemas: 0, bases_datos: 0, terceros: 0, elementos: 0, flujos: 0, flujos_a_terceros: 0,
      transferencias_internacionales: 0, transferencias_sin_garantia: 0, elementos_con_sensibles: 0, flujos_con_sensibles: 0,
      elementos_con_nna: 0, fuera_de_chile: 0, proveedores_ia: 0, categorias_en_uso: 0, categorias_sensibles_en_uso: 0,
      titulares_en_uso: 0, paises: [], pendientes_revision: 0, ...extra,
    },
    conteo_hallazgos: { "Crítica": 0, "Alta": 0, "Media": 0, "Baja": 0 },
    completitud: { porcentaje: 0, pendientes: [] },
    limites: { max_elementos: 300, max_flujos: 800 },
    catalogo_version: "x",
    ...otros,
  });

  it("con el mapa vacío, el siguiente paso es registrar los sistemas", () => {
    const pasos = pasosGuia(vista());
    expect(pasos.map((p) => p.id)).toEqual(["internos", "terceros", "flujos", "completar", "confirmar", "riesgos", "rat"]);
    expect(siguientePaso(pasos).id).toBe("internos");
    expect(pasos.find((p) => p.id === "flujos")?.accion).toBeUndefined();   // con menos de 2 elementos
  });

  it("avanza según lo que ya está listo y lo que falta", () => {
    const e = { id: 1 } as VistaMapa["elementos"][number];
    const v = vista({ sistemas: 2, terceros: 1, flujos: 2, pendientes_revision: 3 }, {
      elementos: [e, { ...e, id: 2 }, { ...e, id: 3 }],
      completitud: { porcentaje: 80, pendientes: [{ tipo: "elemento", id: 1, nombre: "CRM", faltan: ["país"], por_confirmar: true }] },
      conteo_hallazgos: { "Crítica": 1, "Alta": 0, "Media": 0, "Baja": 0 },
    });
    const pasos = pasosGuia(v);
    expect(pasos.filter((p) => p.listo).map((p) => p.id)).toEqual(["internos", "terceros", "flujos"]);
    expect(siguientePaso(pasos).id).toBe("completar");
    expect(pasos.find((p) => p.id === "confirmar")?.texto).toMatch(/3 registros por confirmar/);
    expect(pasos.find((p) => p.id === "riesgos")?.accion?.tipo).toBe("ver_riesgos");
  });
});
