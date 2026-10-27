/**
 * HU-27/HU-28 · POST /bff/admin/login
 *
 * Navegador → { email, password }   ← 200 { adminId, expiraEn } + cookie httpOnly del admin
 *
 * Usa el login que ya existía (POST /api/auth/login). La contraseña viaja solo en el cuerpo.
 */
import type { NextRequest } from "next/server";
import {
  BackendNoDisponibleError,
  jsonSinCache,
  llamarBackend,
  respuestaError,
  sinBackend,
} from "@/lib/servidor/backend";
import { errorAdminDesdeBackend, guardarCookieAdmin } from "@/lib/servidor/backendAdmin";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { sesionAdminDelToken } from "@/lib/servidor/sesionAdmin";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const datos = (await req.json().catch(() => null)) as { email?: unknown; password?: unknown } | null;
  const email = typeof datos?.email === "string" ? datos.email.trim() : "";
  const password = typeof datos?.password === "string" ? datos.password : "";
  if (!email || email.length > 100 || !password || password.length > 200) {
    return respuestaError(422, { codigo: "DATOS_INVALIDOS", mensaje: "Ingresa tu correo y tu contraseña." });
  }

  let res: Response;
  try {
    res = await llamarBackend("/api/auth/login", { metodo: "POST", json: { email, password }, ip: ipCliente(req.headers) });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (res.status === 401) {
    return respuestaError(401, { codigo: "CREDENCIALES_INVALIDAS", mensaje: "Correo o contraseña incorrectos." });
  }
  if (!res.ok) return errorAdminDesdeBackend(res);

  const login = (await res.json().catch(() => null)) as { access_token?: unknown; rol?: unknown } | null;
  const token = typeof login?.access_token === "string" ? login.access_token : "";
  const sesion = sesionAdminDelToken(token);
  if (login?.rol !== "admin_therion" || !sesion) {
    return respuestaError(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "Respuesta inesperada del servidor." });
  }
  const salida = jsonSinCache({ adminId: sesion.adminId, expiraEn: sesion.expiraEn });
  guardarCookieAdmin(salida, token, sesion.expiraEn);
  return salida;
}
