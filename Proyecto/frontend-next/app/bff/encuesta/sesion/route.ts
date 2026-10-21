/**
 * HU-19 · Sesión del encuestado.
 *   GET    /bff/encuesta/sesion → { activa: true, evaluacionId, expiraEn } | { activa: false }
 *   DELETE /bff/encuesta/sesion → 204 (cierra la sesión en este dispositivo)
 *
 * El GET confirma con el backend (GET /api/auth/me) que el token siga habilitado: una
 * supresión ARCOP aprobada o una clave regenerada lo invalidan antes de que venza.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import type { Sesion } from "@/lib/encuesta/contratos";
import { BackendNoDisponibleError, borrarCookie, jsonSinCache, llamarBackend, respuestaError, sinBackend } from "@/lib/servidor/backend";
import { esMismoOrigen } from "@/lib/servidor/peticion";
import { COOKIE_SESION, sesionDelToken } from "@/lib/servidor/sesion";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const token = req.cookies.get(COOKIE_SESION)?.value;
  const sesion = sesionDelToken(token);
  if (!token || !sesion) {
    const res = jsonSinCache({ activa: false } satisfies Sesion);
    if (token) borrarCookie(res);
    return res;
  }
  let me: Response;
  try {
    me = await llamarBackend("/api/auth/me", { token });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (me.status === 401) {
    const res = jsonSinCache({ activa: false } satisfies Sesion);
    borrarCookie(res);
    return res;
  }
  if (!me.ok) return respuestaError(me.status, { codigo: `HTTP_${me.status}`, mensaje: "" });
  return jsonSinCache({ activa: true, evaluacionId: sesion.evaluacionId, expiraEn: sesion.expiraEn } satisfies Sesion);
}

export async function DELETE(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const res = new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  borrarCookie(res);
  return res;
}
