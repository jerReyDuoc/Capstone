/**
 * HU-28 · POST /bff/cliente/login
 *
 * Navegador → { email, password }   ← 200 { expiraEn } + cookie httpOnly del cliente
 *
 * El token de FastAPI (POST /api/auth/cliente) queda SOLO en la cookie: nunca llega al
 * JavaScript, a la URL ni a los logs. La IP real va a la API para su límite de intentos.
 */
import type { NextRequest } from "next/server";
import {
  BackendNoDisponibleError,
  jsonSinCache,
  llamarBackend,
  respuestaError,
  sinBackend,
} from "@/lib/servidor/backend";
import { errorClienteDesdeBackend, guardarCookieCliente } from "@/lib/servidor/backendCliente";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { sesionClienteDelToken } from "@/lib/servidor/sesionCliente";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const datos = (await req.json().catch(() => null)) as { email?: unknown; password?: unknown } | null;
  const email = typeof datos?.email === "string" ? datos.email.trim() : "";
  const password = typeof datos?.password === "string" ? datos.password : "";
  if (!email || email.length > 200 || !password || password.length > 200) {
    return respuestaError(422, { codigo: "DATOS_INVALIDOS", mensaje: "Ingresa tu correo y tu contraseña." });
  }

  let res: Response;
  try {
    res = await llamarBackend("/api/auth/cliente", { metodo: "POST", json: { email, password }, ip: ipCliente(req.headers) });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (res.status === 401) {
    // Mismo mensaje exista o no el correo (HU-28 criterio 3)
    return respuestaError(401, { codigo: "CREDENCIALES_INVALIDAS", mensaje: "Correo o contraseña incorrectos." });
  }
  if (!res.ok) return errorClienteDesdeBackend(res);

  const login = (await res.json().catch(() => null)) as { access_token?: unknown; rol?: unknown } | null;
  const token = typeof login?.access_token === "string" ? login.access_token : "";
  const sesion = sesionClienteDelToken(token);
  if (login?.rol !== "cliente" || !sesion) {
    return respuestaError(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "Respuesta inesperada del servidor." });
  }
  const salida = jsonSinCache({ expiraEn: sesion.expiraEn });
  guardarCookieCliente(salida, token, sesion.expiraEn);
  return salida;
}
