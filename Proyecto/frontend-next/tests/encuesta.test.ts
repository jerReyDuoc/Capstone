/**
 * HU-19 · Pruebas de la lógica pura del flujo público (sin red ni navegador).
 */
import { describe, expect, it } from "vitest";
import {
  cuerpoIniciarBackend,
  formatearClave,
  normalizarClave,
  parseEmailEntrada,
  parseErrorBackend,
  parseIniciadaBackend,
  parseIniciarEntrada,
  parseLimites,
  parseLoginEncuestado,
  parseRetomarEntrada,
  parseRubros,
} from "@/lib/encuesta/contratos";
import { duracionLegible, horaDeReinicio, mensajeDeError } from "@/lib/encuesta/errores";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { autorizarRuta, cuerpoRespuestaEsDeLaSesion, filtrarQuery } from "@/lib/servidor/proxy";
import { leerToken, opcionesCookie, sesionDelToken } from "@/lib/servidor/sesion";
import { AVISO_LEGAL_VERSION } from "@/lib/avisoLegal";

const b64url = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
const token = (o: object) => `${b64url(o)}.firma`;

describe("contratos · iniciar (criterio 1)", () => {
  it("acepta aviso + rubro + captcha y arma el cuerpo del backend sin email", () => {
    const r = parseIniciarEntrada({ rubroId: 3, avisoVersion: AVISO_LEGAL_VERSION, avisoAceptado: true, captchaToken: "t" });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(cuerpoIniciarBackend(r.valor)).toEqual({
      rubro_id: 3,
      aviso_legal: { version: AVISO_LEGAL_VERSION, aceptado: true },
      captcha_token: "t",
    });
    expect(JSON.stringify(cuerpoIniciarBackend(r.valor))).not.toContain("email");
  });

  it("rechaza aviso no aceptado y rubro inválido", () => {
    expect(parseIniciarEntrada({ rubroId: 3, avisoVersion: "v", avisoAceptado: false, captchaToken: "t" })).toEqual({
      ok: false,
      error: "aviso no aceptado",
    });
    expect(parseIniciarEntrada({ rubroId: 0, avisoVersion: "v", avisoAceptado: true, captchaToken: "t" }).ok).toBe(false);
    expect(parseIniciarEntrada({ rubroId: "3", avisoVersion: "v", avisoAceptado: true, captchaToken: "t" }).ok).toBe(false);
  });

  it("valida la respuesta del backend", () => {
    const valida = { evaluacion_id: 7, clave_acceso: "ABCD-EF12-3456", access_token: "a.b", token_type: "bearer", expira_en: 2_000_000_000 };
    expect(parseIniciadaBackend(valida).ok).toBe(true);
    expect(parseIniciadaBackend({ ...valida, clave_acceso: "abc" }).ok).toBe(false);
    expect(parseIniciadaBackend({ ...valida, access_token: "sin-punto" }).ok).toBe(false);
  });

  it("ordena los rubros y tolera nombres vacíos", () => {
    expect(parseRubros([{ id: 2, nombre_rubro: "Salud" }, { id: 1, nombre_rubro: "Banca y Finanzas" }, { id: 9, nombre_rubro: null }, { x: 1 }])).toEqual([
      { id: 1, nombre: "Banca y Finanzas" },
      { id: 9, nombre: "Rubro 9" },
      { id: 2, nombre: "Salud" },
    ]);
    expect(parseRubros(null)).toEqual([]);
  });
});

describe("contratos · retomar y email (criterio 2)", () => {
  it("normaliza la clave como el backend", () => {
    expect(normalizarClave("abcd-ef12 3456")).toBe("ABCDEF123456");
    expect(formatearClave("abcdef123456xyz")).toBe("ABCD-EF12-3456");
    expect(parseRetomarEntrada({ evaluacionId: "42", clave: "abcd ef12 3456" })).toEqual({
      ok: true,
      valor: { evaluacionId: 42, clave: "ABCDEF123456" },
    });
    expect(parseRetomarEntrada({ evaluacionId: "", clave: "ABCDEF123456" }).ok).toBe(false);
    expect(parseRetomarEntrada({ evaluacionId: 42, clave: "corta" }).ok).toBe(false);
  });

  it("el login solo vale para el rol encuestado", () => {
    const base = { access_token: "a.b", token_type: "bearer", usuario_id: 5, expira_en_min: 480 };
    expect(parseLoginEncuestado({ ...base, rol: "encuestado" }).ok).toBe(true);
    expect(parseLoginEncuestado({ ...base, rol: "admin_therion" }).ok).toBe(false);
  });

  it("el email es opcional: vacío o null lo borra, inválido se rechaza", () => {
    expect(parseEmailEntrada({ email: "" })).toEqual({ ok: true, valor: { email: null } });
    expect(parseEmailEntrada({ email: null })).toEqual({ ok: true, valor: { email: null } });
    expect(parseEmailEntrada({ email: " Ana@Empresa.CL " })).toEqual({ ok: true, valor: { email: "ana@empresa.cl" } });
    expect(parseEmailEntrada({ email: "ana@empresa" }).ok).toBe(false);
  });
});

describe("sesión · cookie y token", () => {
  it("la cookie es httpOnly, SameSite=Lax y Path=/", () => {
    const o = opcionesCookie(3600);
    expect(o).toMatchObject({ httpOnly: true, sameSite: "lax", path: "/", maxAge: 3600 });
    expect(opcionesCookie(-5).maxAge).toBe(0);
  });

  it("lee la evaluación y el vencimiento del token del encuestado", () => {
    const t = token({ sub: 12, rol: "encuestado", exp: 2_000 });
    expect(leerToken(t)).toEqual({ sub: 12, rol: "encuestado", exp: 2_000 });
    expect(sesionDelToken(t, 1_000)).toEqual({ evaluacionId: 12, expiraEn: 2_000 });
    expect(sesionDelToken(t, 2_000)).toBeNull(); // vencido
    expect(sesionDelToken(token({ sub: 1, rol: "admin_therion", exp: 9e9 }), 1)).toBeNull();
    expect(sesionDelToken("basura", 1)).toBeNull();
    expect(sesionDelToken(undefined, 1)).toBeNull();
  });
});

describe("proxy · lista blanca y aislamiento (criterio 2)", () => {
  it("permite las rutas del encuestado solo para su evaluación", () => {
    expect(autorizarRuta("GET", ["evaluaciones", "12", "progreso"], 12)).toEqual({ ok: true, ruta: "evaluaciones/12/progreso", archivo: false });
    expect(autorizarRuta("GET", ["evaluaciones", "13", "progreso"], 12)).toEqual({ ok: false, status: 404 });
    expect(autorizarRuta("POST", ["evaluaciones", "12", "completar"], 12).ok).toBe(true);
    expect(autorizarRuta("POST", ["respuestas"], 12)).toEqual({ ok: true, ruta: "respuestas/", archivo: false });
    expect(autorizarRuta("POST", ["respuestas", "5", "evidencias"], 12)).toEqual({ ok: true, ruta: "respuestas/5/evidencias", archivo: true });
    expect(autorizarRuta("GET", ["encuesta-publica", "limites"], 12).ok).toBe(true);
  });

  it("bloquea rutas de admin, listados globales y trucos de ruta", () => {
    for (const [m, seg] of [
      ["GET", ["evaluaciones"]],
      ["PATCH", ["respuestas", "5", "revision"]],
      ["PATCH", ["evaluaciones", "12", "prueba"]],
      ["GET", ["ia", "metricas"]],
      ["GET", ["seguridad", "eventos"]],
      ["POST", ["encuesta-publica", "iniciar"]],
      ["GET", ["evaluaciones", "..", "1"]],
      ["GET", ["evaluaciones", "12%2F..", "progreso"]],
      ["DELETE", ["evaluaciones", "12"]],
    ] as const) {
      expect(autorizarRuta(m, [...seg], 12).ok, `${m} ${seg.join("/")}`).toBe(false);
    }
  });

  it("POST /respuestas debe ser de la evaluación de la sesión", () => {
    expect(cuerpoRespuestaEsDeLaSesion({ evaluacion_id: 12, matriz_control_id: 1 }, 12)).toBe(true);
    expect(cuerpoRespuestaEsDeLaSesion({ evaluacion_id: 13 }, 12)).toBe(false);
    expect(cuerpoRespuestaEsDeLaSesion(null, 12)).toBe(false);
  });

  it("solo reenvía parámetros de consulta conocidos", () => {
    expect(filtrarQuery(new URLSearchParams("page=2&size=100&token=x&evaluacion=9"))).toBe("?page=2&size=100");
    expect(filtrarQuery(new URLSearchParams(""))).toBe("");
  });
});

describe("petición · IP y mismo origen (criterio 3)", () => {
  it("toma la IP agregada por el proxy de confianza, no la que inventa el cliente", () => {
    const h = new Headers({ "x-forwarded-for": "1.1.1.1, 203.0.113.9, 10.0.0.2" });
    expect(ipCliente(h, 0)).toBe("10.0.0.2");
    expect(ipCliente(h, 1)).toBe("203.0.113.9");
    expect(ipCliente(new Headers({ "x-real-ip": "198.51.100.4" }), 0)).toBe("198.51.100.4");
    expect(ipCliente(new Headers({ "x-forwarded-for": "<script>" }), 0)).toBe("desconocida");
  });

  it("exige mismo origen en mutaciones (CSRF)", () => {
    expect(esMismoOrigen(new Headers({ "sec-fetch-site": "same-origin" }))).toBe(true);
    expect(esMismoOrigen(new Headers({ "sec-fetch-site": "cross-site" }))).toBe(false);
    expect(esMismoOrigen(new Headers({ origin: "https://app.cl", host: "app.cl" }))).toBe(true);
    expect(esMismoOrigen(new Headers({ origin: "https://malo.cl", host: "app.cl" }))).toBe(false);
    expect(esMismoOrigen(new Headers({ host: "app.cl" }))).toBe(false);
  });
});

describe("errores · mensajes y cuota del LLM (criterio 3)", () => {
  it("convierte el error de FastAPI y conserva Retry-After / reinicio", () => {
    const e = parseErrorBackend(429, { detail: { codigo: "CUOTA_LLM_AGOTADA", mensaje: "x", reinicia_en: "2026-10-22T03:00:00Z" } }, "3600");
    expect(e).toEqual({ codigo: "CUOTA_LLM_AGOTADA", mensaje: "x", reiniciaEn: "2026-10-22T03:00:00Z", reintentarEnS: 3600 });
    expect(parseErrorBackend(404, { detail: "Evaluación no encontrada" })).toEqual({ codigo: "HTTP_404", mensaje: "Evaluación no encontrada" });
    expect(parseErrorBackend(422, { detail: [{ loc: ["body"] }] }).codigo).toBe("DATOS_INVALIDOS");
  });

  it("cada código tiene un mensaje y una acción", () => {
    expect(mensajeDeError({ codigo: "LIMITE_EVALUACIONES", mensaje: "" }).accion).toBe("retomar");
    expect(mensajeDeError({ codigo: "CUOTA_LLM_AGOTADA", mensaje: "" }).accion).toBe("esperar");
    expect(mensajeDeError({ codigo: "AVISO_DESACTUALIZADO", mensaje: "" }).accion).toBe("recargar");
    expect(mensajeDeError({ codigo: "RARO", mensaje: "detalle del servidor" }).detalle).toBe("detalle del servidor");
  });

  it("muestra la hora de reinicio en Chile y duraciones legibles", () => {
    expect(horaDeReinicio("2026-10-22T03:00:00Z")).toBe("00:00");
    expect(horaDeReinicio("no-es-fecha")).toBeNull();
    expect(duracionLegible(30)).toBe("30 s");
    expect(duracionLegible(600)).toBe("10 min");
    expect(duracionLegible(3900)).toBe("1 h 5 min");
  });
});
