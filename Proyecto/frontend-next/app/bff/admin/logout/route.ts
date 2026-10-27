/**
 * HU-27/HU-28 · POST /bff/admin/logout — cierra la sesión del administrador.
 *
 * HU-28: primero la cierra en el servidor (POST /api/auth/logout: el token queda revocado
 * aunque alguien lo hubiera copiado) y después borra la cookie, responda o no la API.
 */
import type { NextRequest } from "next/server";
import { cerrarSesionEnBackend, jsonSinCache, respuestaError } from "@/lib/servidor/backend";
import { borrarCookieAdmin } from "@/lib/servidor/backendAdmin";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { COOKIE_ADMIN } from "@/lib/servidor/sesionAdmin";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const revocada = await cerrarSesionEnBackend(req.cookies.get(COOKIE_ADMIN)?.value, ipCliente(req.headers));
  const salida = jsonSinCache({ ok: true, revocadaEnServidor: revocada });
  borrarCookieAdmin(salida);
  return salida;
}
