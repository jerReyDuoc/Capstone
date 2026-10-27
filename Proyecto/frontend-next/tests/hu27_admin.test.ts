/**
 * HU-27 · Pruebas de la lógica pura del panel interno y de la activación (sin red ni navegador).
 */
import { describe, expect, it } from "vitest";
import { formatearRut, rutValido, seleccionable, type Solicitud } from "@/lib/admin/api";
import { problemasContrasena, tokenActivacionValido, tokenDesdeFragmento } from "@/lib/activacion";
import { autorizarRutaAdmin, filtrarQueryAdmin } from "@/lib/servidor/proxyAdmin";
import { opcionesCookieAdmin, sesionAdminDelToken } from "@/lib/servidor/sesionAdmin";

const b64url = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
const token = (o: object) => `${b64url(o)}.firma`;
const ahora = 1_800_000_000;

describe("proxy del panel interno · lista blanca", () => {
  it("deja pasar solo las rutas de HU-27 con su método", () => {
    expect(autorizarRutaAdmin("GET", ["admin", "contrataciones"])).toEqual({ ok: true, ruta: "admin/contrataciones" });
    expect(autorizarRutaAdmin("PATCH", ["admin", "contrataciones", "7"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "empresas"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "empresas", "3", "evaluaciones"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "empresas", "3", "usuario", "activacion"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["admin", "bitacora"]).ok).toBe(true);
    expect(autorizarRutaAdmin("GET", ["rubros"]).ok).toBe(true);
  });

  it("rechaza métodos, rutas y segmentos no previstos", () => {
    expect(autorizarRutaAdmin("DELETE", ["admin", "empresas", "3"]).ok).toBe(false);
    expect(autorizarRutaAdmin("PATCH", ["admin", "empresas", "3"]).ok).toBe(false);
    expect(autorizarRutaAdmin("GET", ["ia", "metricas"]).ok).toBe(false);
    expect(autorizarRutaAdmin("GET", ["admin", "..", "ia"]).ok).toBe(false);
    expect(autorizarRutaAdmin("GET", ["admin", "empresas", "3%2F4"]).ok).toBe(false);
    expect(autorizarRutaAdmin("GET", []).ok).toBe(false);
  });

  it("filtra la query a parámetros conocidos y con formato válido", () => {
    const q = new URLSearchParams("estado=contratada&size=50&evil=1&estado=hackeado&accion=empresa.creada");
    expect(filtrarQueryAdmin(q)).toBe("?estado=contratada&size=50&accion=empresa.creada");
    expect(filtrarQueryAdmin(new URLSearchParams("page=abc"))).toBe("");
  });
});

describe("sesión del administrador", () => {
  it("solo acepta tokens vigentes del rol admin_therion", () => {
    expect(sesionAdminDelToken(token({ sub: 1, rol: "admin_therion", exp: ahora + 60 }), ahora)).toEqual({
      adminId: 1,
      expiraEn: ahora + 60,
    });
    expect(sesionAdminDelToken(token({ sub: 1, rol: "admin_therion", exp: ahora - 1 }), ahora)).toBeNull();
    expect(sesionAdminDelToken(token({ sub: 9, rol: "encuestado", exp: ahora + 60 }), ahora)).toBeNull();
    expect(sesionAdminDelToken(token({ sub: 9, rol: "cliente", exp: ahora + 60 }), ahora)).toBeNull();
    expect(sesionAdminDelToken("basura", ahora)).toBeNull();
  });

  it("la cookie es httpOnly y SameSite=Strict", () => {
    const o = opcionesCookieAdmin(120.7);
    expect(o).toMatchObject({ httpOnly: true, sameSite: "strict", path: "/", maxAge: 120 });
  });
});

describe("enlace de activación", () => {
  const t = "A".repeat(43);

  it("lee el token del fragmento y valida su formato", () => {
    expect(tokenDesdeFragmento(`#token=${t}`)).toBe(t);
    expect(tokenDesdeFragmento(`token=${t}`)).toBe(t);
    expect(tokenDesdeFragmento("#token=corto")).toBeNull();
    expect(tokenDesdeFragmento("#otra=cosa")).toBeNull();
    expect(tokenActivacionValido(`${t}<script>`)).toBe(false);
  });

  it("anticipa las reglas de la contraseña del backend", () => {
    expect(problemasContrasena("Gobernanza2026segura")).toEqual([]);
    expect(problemasContrasena("Corta1")).toContain("Debe tener al menos 12 caracteres.");
    expect(problemasContrasena("solamenteletras")).toContain("Debe combinar letras y números.");
    expect(problemasContrasena(" Espacio2026abc ")).toContain("No puede empezar ni terminar con espacios.");
  });
});

describe("formulario de alta", () => {
  it("valida el RUT con su dígito verificador y lo formatea", () => {
    expect(rutValido("76.086.428-5")).toBe(true);
    expect(rutValido("760864285")).toBe(true);
    expect(rutValido("76.086.428-4")).toBe(false);
    expect(rutValido("1-9")).toBe(false);
    expect(formatearRut("76086428-5")).toBe("76.086.428-5");
  });

  it("solo se eligen solicitudes contratadas, autorizadas, completadas y sin empresa", () => {
    const base: Solicitud = {
      id: 1, estado: "contratada", autoriza_migracion: true, empresa_id: null, fecha_creacion: "2026-10-26",
      razon_social_declarada: null, contacto: { nombre: "Ana", email: "a@b.cl", telefono: null },
      evaluacion: { id: 5, completada: true },
    };
    expect(seleccionable(base)).toBe(true);
    expect(seleccionable({ ...base, estado: "pendiente" })).toBe(false);
    expect(seleccionable({ ...base, autoriza_migracion: false })).toBe(false);
    expect(seleccionable({ ...base, evaluacion: { id: 5, completada: false } })).toBe(false);
    expect(seleccionable({ ...base, empresa_id: 3 })).toBe(false);
  });
});
