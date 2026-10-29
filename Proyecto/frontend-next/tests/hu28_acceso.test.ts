/**
 * HU-28 · Pruebas de la lógica pura del inicio/cierre de sesión y la recuperación (sin red ni navegador).
 */
import { describe, expect, it } from "vitest";
import { emailValido, INICIO_DE, LOGIN_DE, mensajeLogin, motivoLogin, TEXTO_MOTIVO, tipoCuenta } from "@/lib/acceso";
import { diasParaTermino, fechaCorta } from "@/lib/empresa";
import { autorizarRutaAdmin, filtrarQueryAdmin } from "@/lib/servidor/proxyAdmin";
import { autorizarRutaCliente } from "@/lib/servidor/proxyCliente";
import { sesionAdminDelToken } from "@/lib/servidor/sesionAdmin";
import { COOKIE_CLIENTE, opcionesCookieCliente, sesionClienteDelToken } from "@/lib/servidor/sesionCliente";
import { sesionDelToken } from "@/lib/servidor/sesion";

const b64url = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
const token = (o: object) => `${b64url(o)}.firma`;
const ahora = 1_800_000_000;

describe("cookie de sesión del cliente", () => {
  it("es httpOnly, SameSite=Lax y propia (no la del encuestado ni la del admin)", () => {
    expect(opcionesCookieCliente(3600)).toEqual({ httpOnly: true, secure: false, sameSite: "lax", path: "/", maxAge: 3600 });
    expect(opcionesCookieCliente(-5).maxAge).toBe(0);
    expect(COOKIE_CLIENTE).toBe("cai_cliente"); // __Host-cai_cliente en producción
  });

  it("solo acepta tokens vigentes con rol cliente (y el sid no molesta)", () => {
    const t = token({ sub: 4, rol: "cliente", exp: ahora + 60, sid: "x".repeat(32) });
    expect(sesionClienteDelToken(t, ahora)).toEqual({ usuarioId: 4, expiraEn: ahora + 60 });
    expect(sesionClienteDelToken(token({ sub: 4, rol: "cliente", exp: ahora - 1 }), ahora)).toBeNull();
    expect(sesionClienteDelToken(token({ sub: 4, rol: "admin_therion", exp: ahora + 60 }), ahora)).toBeNull();
    expect(sesionClienteDelToken(token({ sub: 4, rol: "encuestado", exp: ahora + 60 }), ahora)).toBeNull();
    expect(sesionClienteDelToken(undefined, ahora)).toBeNull();
    expect(sesionClienteDelToken("basura", ahora)).toBeNull();
  });

  it("un token de cliente no abre la sesión del encuestado ni la del admin", () => {
    const t = token({ sub: 4, rol: "cliente", exp: ahora + 60 });
    expect(sesionDelToken(t, ahora)).toBeNull();
    expect(sesionAdminDelToken(t, ahora)).toBeNull();
  });
});

describe("proxy del cliente · lista blanca", () => {
  it("deja pasar el espacio de la empresa y las LECTURAS de sus evaluaciones", () => {
    expect(autorizarRutaCliente("GET", ["cliente", "empresa"])).toEqual({
      ok: true, ruta: "cliente/empresa", binario: false, conIp: false, archivo: false, timeoutMs: undefined,
    });
    expect(autorizarRutaCliente("GET", ["evaluaciones"]).ok).toBe(true);
    for (const sub of ["respuestas", "resumen", "comparativa", "progreso", "plan-formativo"]) {
      expect(autorizarRutaCliente("GET", ["evaluaciones", "12", sub]).ok).toBe(true);
    }
    const pdf = autorizarRutaCliente("GET", ["evaluaciones", "12", "informe", "pdf"]);
    expect(pdf.ok && pdf.binario).toBe(true);
    const correo = autorizarRutaCliente("POST", ["evaluaciones", "12", "informe", "enviar"]);
    expect(correo.ok && correo.conIp).toBe(true);
    expect(autorizarRutaCliente("GET", ["brechas"]).ok).toBe(true);
  });

  it("no deja reescribir el historial migrado ni llegar a lo de Therion Labs", () => {
    // HU-29: POST respuestas, /filtro y /completar ahora pasan (reevaluación con la sesión del
    // cliente); el historial migrado está completado y el backend rechaza cambios (409).
    // Siguen fuera: editar con PUT, recalcular con /cerrar y borrar evaluaciones.
    expect(autorizarRutaCliente("PUT", ["respuestas", "40"]).ok).toBe(false);
    expect(autorizarRutaCliente("POST", ["evaluaciones", "12", "cerrar"]).ok).toBe(false);
    expect(autorizarRutaCliente("PATCH", ["evaluaciones", "12", "prueba"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["admin", "empresas"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["arcop", "solicitudes"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["ia", "metricas"]).ok).toBe(false);
    expect(autorizarRutaCliente("DELETE", ["evaluaciones", "12"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["evaluaciones", "..", "admin"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", ["evaluaciones", "1%2F2"]).ok).toBe(false);
    expect(autorizarRutaCliente("GET", []).ok).toBe(false);
  });
});

describe("panel interno · evaluaciones (HU-28)", () => {
  it("el proxy del admin deja pasar el listado de evaluaciones con sus filtros", () => {
    expect(autorizarRutaAdmin("GET", ["admin", "evaluaciones"]).ok).toBe(true);
    expect(autorizarRutaAdmin("POST", ["admin", "evaluaciones"]).ok).toBe(false);
    const q = new URLSearchParams("estado=completada&origen=publica&empresa_id=3&incluir_prueba=true&origen=x");
    expect(filtrarQueryAdmin(q)).toBe("?estado=completada&origen=publica&empresa_id=3&incluir_prueba=true");
    expect(filtrarQueryAdmin(new URLSearchParams("estado=borrada"))).toBe("");
  });
});

describe("mensajes y rutas de acceso", () => {
  it("el error de login nunca distingue un correo inexistente de una contraseña mala", () => {
    expect(mensajeLogin("CREDENCIALES_INVALIDAS")).toBe("Correo o contraseña incorrectos.");
    expect(mensajeLogin("CREDENCIALES_INVALIDAS")).not.toMatch(/no existe|no registrad|no encontr/i);
  });

  it("el bloqueo por intentos dice cuánto esperar", () => {
    expect(mensajeLogin("DEMASIADOS_INTENTOS", 600)).toContain("10 minutos");
    expect(mensajeLogin("DEMASIADOS_INTENTOS", 30)).toContain("1 minuto ");
    expect(mensajeLogin("DEMASIADOS_INTENTOS")).toMatch(/unos minutos/);
    expect(mensajeLogin("CUALQUIER_COSA")).toBeTruthy();
  });

  it("solo acepta motivos conocidos en ?motivo= y tipos de cuenta válidos", () => {
    expect(motivoLogin("salida")).toBe("salida");
    expect(motivoLogin("<script>")).toBeUndefined();
    expect(Object.keys(TEXTO_MOTIVO).sort()).toEqual(["activada", "restablecida", "salida", "sesion"]);
    expect(tipoCuenta("admin")).toBe("admin");
    expect(tipoCuenta("otro")).toBe("cliente");
    expect(LOGIN_DE).toEqual({ cliente: "/ingresar", admin: "/admin/login" });
    expect(INICIO_DE).toEqual({ cliente: "/empresa", admin: "/admin/clientes" });
  });

  it("valida el correo antes de pedir la recuperación", () => {
    expect(emailValido("gerencia@acme.cl")).toBe(true);
    expect(emailValido(" gerencia@acme.cl ")).toBe(true);
    expect(emailValido("gerencia@acme")).toBe(false);
    expect(emailValido("sin-arroba")).toBe(false);
    expect(emailValido(`${"a".repeat(195)}@acme.cl`)).toBe(false);
  });
});

describe("espacio de la empresa", () => {
  it("calcula los días al término del contrato y formatea fechas sin zona horaria", () => {
    const hoy = new Date(2026, 9, 27); // 27-10-2026
    expect(diasParaTermino("2026-11-26", hoy)).toBe(30);
    expect(diasParaTermino("2026-10-27", hoy)).toBe(0);
    expect(diasParaTermino("2026-10-20", hoy)).toBe(-7);
    expect(fechaCorta("2026-10-27T03:00:00")).toBe("27-10-2026");
    expect(fechaCorta(null)).toBe("—");
  });
});
