/**
 * HU-27/HU-28 · Cookie de sesión del ADMINISTRADOR (compatible con Edge: la usa middleware.ts).
 *
 * Igual que la del encuestado (sesion.ts): cookie httpOnly que el navegador no puede leer;
 * el token lo firma y lo verifica FastAPI en cada petición. Aquí solo se lee su contenido
 * para saber si hay sesión de admin vigente (redirección y segunda barrera del proxy).
 *   - nombre distinto al del encuestado: una misma persona puede probar ambos flujos;
 *   - SameSite=Strict: el panel interno nunca se abre desde un enlace externo.
 */
import { leerToken } from "./sesion";

const PRODUCCION = process.env.NODE_ENV === "production";

export const COOKIE_ADMIN = PRODUCCION ? "__Host-cai_admin" : "cai_admin";
export const ROL_ADMIN = "admin_therion";

export interface OpcionesCookieAdmin {
  httpOnly: true;
  secure: boolean;
  sameSite: "strict";
  path: "/";
  maxAge: number;
}

export function opcionesCookieAdmin(maxAgeS: number): OpcionesCookieAdmin {
  return { httpOnly: true, secure: PRODUCCION, sameSite: "strict", path: "/", maxAge: Math.max(0, Math.floor(maxAgeS)) };
}

/** Sesión de admin vigente según el token, o null. `ahoraS` en segundos epoch. */
export function sesionAdminDelToken(
  token: string | undefined | null,
  ahoraS = Math.floor(Date.now() / 1000),
): { adminId: number; expiraEn: number } | null {
  const datos = leerToken(token);
  if (!datos || datos.rol !== ROL_ADMIN || datos.exp <= ahoraS) return null;
  return { adminId: datos.sub, expiraEn: datos.exp };
}
