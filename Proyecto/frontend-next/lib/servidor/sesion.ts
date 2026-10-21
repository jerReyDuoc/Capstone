/**
 * HU-19 · Cookie de sesión del encuestado (compatible con Edge: la usa middleware.ts).
 *
 * El token lo firma el backend (HMAC). Aquí solo se LEE su contenido para saber a qué
 * evaluación pertenece y cuándo vence (UX y segunda barrera del proxy); quien lo
 * verifica de verdad es FastAPI en cada petición.
 *
 * Por qué cookie httpOnly y no localStorage: un XSS puede leer localStorage, pero no
 * una cookie httpOnly. El token nunca llega al JavaScript del navegador, ni a la URL,
 * ni a los logs.
 *   - __Host-  : solo HTTPS, sin Domain, Path=/ (no la puede pisar un subdominio).
 *   - SameSite=Lax + verificación de Origin en todo lo que no sea GET (ver peticion.ts):
 *     protege de CSRF y permite entrar a /encuesta desde un enlace externo.
 */

const PRODUCCION = process.env.NODE_ENV === "production";

/** En desarrollo (http://localhost) no se puede usar __Host- porque exige Secure. */
export const COOKIE_SESION = PRODUCCION ? "__Host-cai_sesion" : "cai_sesion";

export interface OpcionesCookie {
  httpOnly: true;
  secure: boolean;
  sameSite: "lax";
  path: "/";
  maxAge: number;
}

export function opcionesCookie(maxAgeS: number): OpcionesCookie {
  return {
    httpOnly: true,
    secure: PRODUCCION,
    sameSite: "lax",
    path: "/",
    maxAge: Math.max(0, Math.floor(maxAgeS)),
  };
}

export interface DatosToken {
  sub: number;
  rol: string;
  exp: number;
}

function base64UrlADecodificado(texto: string): string {
  const b64 = texto.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (texto.length % 4)) % 4);
  // atob existe en Edge y en Node ≥ 16
  const binario = atob(b64);
  const bytes = Uint8Array.from(binario, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** Lee (sin verificar la firma) el cuerpo del token: base64url(json).base64url(firma). */
export function leerToken(token: string | undefined | null): DatosToken | null {
  if (!token || token.length > 4096) return null;
  const [cuerpo, firma] = token.split(".");
  if (!cuerpo || !firma) return null;
  try {
    const datos = JSON.parse(base64UrlADecodificado(cuerpo)) as Record<string, unknown>;
    const { sub, rol, exp } = datos;
    if (typeof sub !== "number" || typeof rol !== "string" || typeof exp !== "number") return null;
    return { sub, rol, exp };
  } catch {
    return null;
  }
}

/** Sesión del encuestado vigente según el token, o null. `ahoraS` en segundos epoch. */
export function sesionDelToken(
  token: string | undefined | null,
  ahoraS = Math.floor(Date.now() / 1000),
): { evaluacionId: number; expiraEn: number } | null {
  const datos = leerToken(token);
  if (!datos || datos.rol !== "encuestado" || datos.exp <= ahoraS) return null;
  return { evaluacionId: datos.sub, expiraEn: datos.exp };
}
