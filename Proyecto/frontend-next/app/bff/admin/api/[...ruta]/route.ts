/**
 * HU-27 · Proxy autenticado del panel interno: /bff/admin/api/<ruta> → FastAPI /api/<ruta>
 *
 * - Lee el token del admin de su cookie httpOnly y lo envía como Bearer.
 * - Solo reenvía la lista blanca de lib/servidor/proxyAdmin.ts (lo demás → 404).
 * - Todo lo que no es GET exige mismo origen (CSRF) y cuerpo JSON acotado.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { BackendNoDisponibleError, llamarBackend, respuestaError, sinBackend } from "@/lib/servidor/backend";
import { borrarCookieAdmin, errorAdminDesdeBackend } from "@/lib/servidor/backendAdmin";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { autorizarRutaAdmin, filtrarQueryAdmin, MAX_BYTES_JSON_ADMIN } from "@/lib/servidor/proxyAdmin";
import { COOKIE_ADMIN, sesionAdminDelToken } from "@/lib/servidor/sesionAdmin";

export const dynamic = "force-dynamic";

type Contexto = { params: Promise<{ ruta: string[] }> };

async function manejar(req: NextRequest, { params }: Contexto): Promise<NextResponse> {
  const metodo = req.method.toUpperCase();
  if (metodo !== "GET" && !esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const token = req.cookies.get(COOKIE_ADMIN)?.value;
  if (!token || !sesionAdminDelToken(token)) {
    const res = respuestaError(401, { codigo: "SESION_EXPIRADA", mensaje: "Tu sesión de administrador terminó." });
    if (token) borrarCookieAdmin(res);
    return res;
  }
  const { ruta } = await params;
  const permiso = autorizarRutaAdmin(metodo, ruta);
  if (!permiso.ok) return respuestaError(404, { codigo: "NO_ENCONTRADO", mensaje: "Recurso no encontrado." });

  let json: unknown = undefined;
  if (metodo !== "GET") {
    const texto = await req.text();
    if (texto.length > MAX_BYTES_JSON_ADMIN) {
      return respuestaError(413, { codigo: "CUERPO_DEMASIADO_GRANDE", mensaje: "Contenido demasiado grande." });
    }
    try {
      json = texto ? JSON.parse(texto) : {};
    } catch {
      return respuestaError(400, { codigo: "JSON_INVALIDO", mensaje: "Cuerpo inválido." });
    }
  }

  let res: Response;
  try {
    res = await llamarBackend(`/api/${permiso.ruta}${filtrarQueryAdmin(req.nextUrl.searchParams)}`, {
      metodo: metodo as "GET" | "POST" | "PATCH",
      json,
      token,
      ip: ipCliente(req.headers),
      timeoutMs: 30_000, // el alta envía el correo de activación
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (!res.ok) return errorAdminDesdeBackend(res);
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
  });
}

export const GET = manejar;
export const POST = manejar;
export const PATCH = manejar;
