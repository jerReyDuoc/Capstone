/**
 * HU-28 · Proxy autenticado del usuario definitivo: /bff/cliente/api/<ruta> → FastAPI /api/<ruta>
 *
 * - Lee el token de la cookie httpOnly del cliente y lo envía como Bearer.
 * - Solo reenvía la lista blanca de lib/servidor/proxyCliente.ts (lo demás → 404).
 * - Todo lo que no es GET exige mismo origen (CSRF) y cuerpo JSON acotado.
 * - El informe PDF y la constancia (HU-26) pasan como binario, con su Content-Disposition.
 * - HU-17: la evidencia de remediación pasa como multipart (stream), con límite de tamaño.
 * - HU-15: el chat del tutor usa además PATCH (nivel) y DELETE (borrar conversación).
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { BackendNoDisponibleError, llamarBackend, respuestaError, sinBackend } from "@/lib/servidor/backend";
import { borrarCookieCliente, errorClienteDesdeBackend } from "@/lib/servidor/backendCliente";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { filtrarQuery } from "@/lib/servidor/proxy";
import { autorizarRutaCliente, MAX_BYTES_ARCHIVO_CLIENTE, MAX_BYTES_JSON_CLIENTE } from "@/lib/servidor/proxyCliente";
import { COOKIE_CLIENTE, sesionClienteDelToken } from "@/lib/servidor/sesionCliente";

export const dynamic = "force-dynamic";

type Contexto = { params: Promise<{ ruta: string[] }> };

async function manejar(req: NextRequest, { params }: Contexto): Promise<NextResponse> {
  const metodo = req.method.toUpperCase();
  if (metodo !== "GET" && !esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const token = req.cookies.get(COOKIE_CLIENTE)?.value;
  if (!token || !sesionClienteDelToken(token)) {
    const res = respuestaError(401, { codigo: "SESION_EXPIRADA", mensaje: "Tu sesión terminó." });
    if (token) borrarCookieCliente(res);
    return res;
  }
  const { ruta } = await params;
  const permiso = autorizarRutaCliente(metodo, ruta);
  if (!permiso.ok) return respuestaError(404, { codigo: "NO_ENCONTRADO", mensaje: "Recurso no encontrado." });

  let json: unknown = undefined;
  let cuerpo: BodyInit | null = null;
  let contentType: string | null = null;
  if (metodo !== "GET" && permiso.archivo) {
    contentType = req.headers.get("content-type");
    const largo = Number(req.headers.get("content-length") ?? "0");
    if (!contentType?.startsWith("multipart/form-data")) {
      return respuestaError(415, { codigo: "TIPO_NO_SOPORTADO", mensaje: "Adjunta el archivo como formulario." });
    }
    if (!largo || largo > MAX_BYTES_ARCHIVO_CLIENTE) {
      return respuestaError(413, { codigo: "ARCHIVO_DEMASIADO_GRANDE", mensaje: "El archivo supera el máximo de 12 MB." });
    }
    cuerpo = req.body;
  } else if (metodo !== "GET") {
    const texto = await req.text();
    if (texto.length > MAX_BYTES_JSON_CLIENTE) {
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
    res = await llamarBackend(`/api/${permiso.ruta}${filtrarQuery(req.nextUrl.searchParams)}`, {
      metodo: metodo as "GET" | "POST" | "PATCH" | "DELETE",
      ...(permiso.archivo ? { cuerpo, contentType } : { json }),
      token,
      ip: permiso.conIp ? ipCliente(req.headers) : undefined,
      timeoutMs: permiso.timeoutMs ?? 15_000,
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (!res.ok) return errorClienteDesdeBackend(res);
  // HU-15: DELETE de una conversación del tutor (204 no admite cuerpo)
  if (res.status === 204) return new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });

  if (permiso.binario) {
    const tipo = res.headers.get("content-type") ?? "";
    if (!tipo.startsWith("application/pdf")) {
      return respuestaError(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "El servidor no devolvió un PDF." });
    }
    const disposicion = res.headers.get("content-disposition");
    return new NextResponse(await res.arrayBuffer(), {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        ...(disposicion && /^attachment; filename="[\w.-]+"$/.test(disposicion) ? { "Content-Disposition": disposicion } : {}),
      },
    });
  }
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
  });
}

export const GET = manejar;
export const POST = manejar;
export const PATCH = manejar; // HU-15: nivel de la conversación del tutor
export const DELETE = manejar; // HU-15: borrar una conversación del tutor
