/**
 * HU-28 · GET /bff/cliente/sesion → { activa: true, expiraEn } | { activa: false }
 *
 * Confirma con el backend (GET /api/auth/me) que la sesión siga abierta: un cierre de
 * sesión en otro lado, un cambio de contraseña o el término del contrato la invalidan
 * antes de que venza el token. Lo usa el panel para saber si mostrar el modo "cliente".
 */
import type { NextRequest } from "next/server";
import { BackendNoDisponibleError, jsonSinCache, llamarBackend, sinBackend } from "@/lib/servidor/backend";
import { borrarCookieCliente } from "@/lib/servidor/backendCliente";
import { COOKIE_CLIENTE, sesionClienteDelToken } from "@/lib/servidor/sesionCliente";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const token = req.cookies.get(COOKIE_CLIENTE)?.value;
  const sesion = sesionClienteDelToken(token);
  if (!token || !sesion) {
    const res = jsonSinCache({ activa: false });
    if (token) borrarCookieCliente(res);
    return res;
  }
  let me: Response;
  try {
    me = await llamarBackend("/api/auth/me", { token });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (!me.ok) {
    const res = jsonSinCache({ activa: false });
    if (me.status === 401) borrarCookieCliente(res);
    return res;
  }
  return jsonSinCache({ activa: true, expiraEn: sesion.expiraEn });
}
