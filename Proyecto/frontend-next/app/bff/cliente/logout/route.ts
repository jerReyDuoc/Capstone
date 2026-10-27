/**
 * HU-28 · POST /bff/cliente/logout — cierra la sesión del usuario definitivo.
 *
 * Primero la cierra en el servidor (el token queda revocado aunque alguien lo hubiera
 * copiado) y después borra la cookie. La cookie se borra siempre, responda o no la API.
 */
import type { NextRequest } from "next/server";
import { cerrarSesionEnBackend, jsonSinCache, respuestaError } from "@/lib/servidor/backend";
import { borrarCookieCliente } from "@/lib/servidor/backendCliente";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { COOKIE_CLIENTE } from "@/lib/servidor/sesionCliente";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const revocada = await cerrarSesionEnBackend(req.cookies.get(COOKIE_CLIENTE)?.value, ipCliente(req.headers));
  const salida = jsonSinCache({ ok: true, revocadaEnServidor: revocada });
  borrarCookieCliente(salida);
  return salida;
}
