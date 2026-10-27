/**
 * HU-28 · Cookie de sesión del USUARIO DEFINITIVO de una empresa cliente (compatible con Edge:
 * la usa middleware.ts).
 *
 * Igual que la del encuestado (sesion.ts) y la del admin (sesionAdmin.ts): cookie httpOnly
 * que el JavaScript del navegador no puede leer; el token lo firma y lo verifica FastAPI en
 * cada petición (y desde HU-28 lleva una sesión revocable en el servidor). Aquí solo se lee
 * su contenido para saber si hay una sesión de cliente vigente (redirecciones y segunda
 * barrera del proxy).
 *   - nombre propio: una misma persona puede tener abierta la encuesta pública y el servicio;
 *   - SameSite=Lax (no Strict): el cliente llega al servicio desde enlaces de correo; los
 *     POST igual exigen mismo origen (peticion.ts: esMismoOrigen) contra CSRF.
 */
import { leerToken } from "./sesion";

const PRODUCCION = process.env.NODE_ENV === "production";

export const COOKIE_CLIENTE = PRODUCCION ? "__Host-cai_cliente" : "cai_cliente";
export const ROL_CLIENTE = "cliente";

export interface OpcionesCookieCliente {
  httpOnly: true;
  secure: boolean;
  sameSite: "lax";
  path: "/";
  maxAge: number;
}

export function opcionesCookieCliente(maxAgeS: number): OpcionesCookieCliente {
  return { httpOnly: true, secure: PRODUCCION, sameSite: "lax", path: "/", maxAge: Math.max(0, Math.floor(maxAgeS)) };
}

/** Sesión de cliente vigente según el token, o null. `ahoraS` en segundos epoch. */
export function sesionClienteDelToken(
  token: string | undefined | null,
  ahoraS = Math.floor(Date.now() / 1000),
): { usuarioId: number; expiraEn: number } | null {
  const datos = leerToken(token);
  if (!datos || datos.rol !== ROL_CLIENTE || datos.exp <= ahoraS) return null;
  return { usuarioId: datos.sub, expiraEn: datos.exp };
}
