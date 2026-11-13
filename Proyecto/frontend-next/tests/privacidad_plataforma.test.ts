/**
 * HU-41 · lógica pura de "Privacidad de la plataforma" (panel interno) y del proxy del admin.
 */
import { describe, expect, it } from "vitest";
import {
  cambiosRopa, codigoBienFormado, columnaMapa, contarPlazos, estadoRegistro, filtrarHallazgos, mensajeCampoRopa,
  nombreDesdeDisposicion, resumenHallazgos,
  type Actividad, type DatosRopa, type ElementoMapa, type Hallazgo, type ResumenPrivacidad,
} from "@/lib/admin/privacidad";
import { autorizarRutaAdmin, filtrarQueryAdmin } from "@/lib/servidor/proxyAdmin";

const hallazgo = (codigo: string, nivel: Hallazgo["nivel"]): Hallazgo => ({
  codigo, nivel, titulo: codigo, detalle: "", recomendacion: "", actividades: [], ajuste: null,
});

const registro = (oficial: boolean): ResumenPrivacidad["registro"] => ({
  huella: "a".repeat(64), huella_legible: "AAAA AAAA", oficial, motivos_borrador: oficial ? [] : ["Falta un plazo"],
  version_siguiente: 3, al_dia: false, cambio_desde_ultima: true, pais_alojamiento: "US",
  pais_alojamiento_nombre: "Estados Unidos",
});

describe("revisión interna", () => {
  it("filtra los hallazgos por nivel", () => {
    const lista = [hallazgo("a", "alto"), hallazgo("b", "medio"), hallazgo("c", "medio")];
    expect(filtrarHallazgos(lista, "todos")).toHaveLength(3);
    expect(filtrarHallazgos(lista, "medio").map((h) => h.codigo)).toEqual(["b", "c"]);
    expect(filtrarHallazgos(lista, "critico")).toEqual([]);
  });

  it("resume los hallazgos en lenguaje simple, sin los niveles en cero", () => {
    expect(resumenHallazgos({ critico: 0, alto: 1, medio: 4, bajo: 0 })).toBe("1 alto · 4 medios");
    expect(resumenHallazgos({ critico: 2 })).toBe("2 críticos");
    expect(resumenHallazgos({})).toBe("Sin hallazgos");
  });

  it("indica si el registro saldrá oficial o como borrador", () => {
    expect(estadoRegistro(registro(true))).toEqual({ texto: "Registro oficial · versión 3", tono: "tone-ok" });
    expect(estadoRegistro(registro(false)).texto).toBe("Borrador · versión 3");
  });

  it("cuenta los plazos que salen de un plazo configurado", () => {
    const act = (dias: (number | null)[]) => ({ plazos: dias.map((d) => ({ dias: d })) }) as unknown as Actividad;
    expect(contarPlazos([act([180, 180]), act([null, 730])])).toEqual({ automaticos: 3, total: 4 });
  });
});

describe("mapa de datos", () => {
  it("ubica cada elemento en su columna", () => {
    const e = (tipo: ElementoMapa["tipo"]) => ({ tipo }) as ElementoMapa;
    expect(columnaMapa(e("sistema"))).toBe("operacion");
    expect(columnaMapa(e("base_datos"))).toBe("almacenamiento");
    expect(columnaMapa(e("tercero"))).toBe("proveedores");
  });
});

describe("datos de Therion Labs para el RoPA", () => {
  const antes: DatosRopa = {
    direccion: "Av. Providencia 1234", correo: "privacidad@therionlabs.cl", telefono: null,
    tiene_dpo: false, dpo_cargo: null, dpo_correo: null,
  };

  it("envía solo lo que cambió y un texto vacío borra el valor", () => {
    expect(cambiosRopa(antes, { ...antes })).toEqual({});
    expect(cambiosRopa(antes, { ...antes, direccion: "  Av. Providencia 1234  ", telefono: "+56 2 2345 6789" }))
      .toEqual({ telefono: "+56 2 2345 6789" });
    expect(cambiosRopa(antes, { ...antes, correo: "  " })).toEqual({ correo: null });
    expect(cambiosRopa(antes, { ...antes, tiene_dpo: true })).toEqual({ tiene_dpo: true });
  });

  it("muestra junto a cada campo lo que falta o lo que rechazó el servidor", () => {
    const faltantes = [{ grupo: "empresa", campo: "correo" as const, mensaje: "Escribe el correo." }];
    expect(mensajeCampoRopa(faltantes, "correo")).toBe("Escribe el correo.");
    expect(mensajeCampoRopa(faltantes, "direccion")).toBeNull();
    expect(mensajeCampoRopa(faltantes, "correo", { campo: "correo", mensaje: "Revisa el formato." })).toBe("Revisa el formato.");
  });
});

describe("informes y verificación", () => {
  it("reconoce solo los códigos de los informes de la plataforma", () => {
    expect(codigoBienFormado("CIA-PLAT-REG-2026-000003-7")).toBe(true);
    expect(codigoBienFormado(" cia-plat-ropa-2026-000012-k ")).toBe(true);
    expect(codigoBienFormado("CIA-REG-2026-000003-7")).toBe(false);
    expect(codigoBienFormado("CIA-PLAT-REG-2026-3-7")).toBe(false);
  });

  it("toma el nombre del archivo del servidor solo si es seguro", () => {
    expect(nombreDesdeDisposicion('attachment; filename="registro_plataforma_v2_2026-11-13.pdf"', "x.pdf"))
      .toBe("registro_plataforma_v2_2026-11-13.pdf");
    expect(nombreDesdeDisposicion('attachment; filename="../otro.pdf"', "respaldo.pdf")).toBe("respaldo.pdf");
    expect(nombreDesdeDisposicion(null, "respaldo.xlsx")).toBe("respaldo.xlsx");
  });
});

describe("proxy del admin (/bff/admin/api)", () => {
  const ok = (metodo: string, ruta: string) => autorizarRutaAdmin(metodo, ruta.split("/")).ok;

  it("deja pasar solo las rutas del registro de la plataforma", () => {
    expect(ok("GET", "admin/privacidad-plataforma")).toBe(true);
    expect(ok("GET", "admin/privacidad-plataforma/actividades/encuesta_publica")).toBe(true);
    expect(ok("PATCH", "admin/privacidad-plataforma/ropa-datos")).toBe(true);
    expect(ok("POST", "admin/privacidad-plataforma/informes")).toBe(true);
    expect(ok("GET", "admin/privacidad-plataforma/informes/verificacion")).toBe(true);
    expect(ok("POST", "admin/privacidad-plataforma/ropa-datos")).toBe(false);
    expect(ok("GET", "admin/privacidad-plataforma/informes/abc/descarga")).toBe(false);
  });

  it("marca como binarias las descargas de PDF y Excel", () => {
    const d = autorizarRutaAdmin("GET", "admin/privacidad-plataforma/informes/12/descarga".split("/"));
    expect(d.ok && d.binario).toBe(true);
    expect(d.ok && d.tipos).toContain("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    const m = autorizarRutaAdmin("GET", "admin/privacidad-plataforma/mapa/descarga".split("/"));
    expect(m.ok && m.tipos).toEqual(["application/pdf"]);
    const j = autorizarRutaAdmin("GET", ["admin", "privacidad-plataforma"]);
    expect(j.ok && j.binario).toBeFalsy();
  });

  it("filtra el código y el formato de la consulta", () => {
    const p = new URLSearchParams({ codigo: "CIA-PLAT-REG-2026-000003-7", formato: "xlsx", otro: "x" });
    expect(filtrarQueryAdmin(p)).toBe("?codigo=CIA-PLAT-REG-2026-000003-7&formato=xlsx");
    expect(filtrarQueryAdmin(new URLSearchParams({ formato: "exe", codigo: "<script>" }))).toBe("");
  });
});
