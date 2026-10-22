/**
 * HU-19 · Proxy autenticado del encuestado: /bff/api/<ruta> → FastAPI /api/<ruta>
 *
 * - Lee el token de la cookie httpOnly y lo envía como Bearer (el navegador no lo ve).
 * - Solo reenvía la lista blanca de lib/servidor/proxy.ts y solo para la evaluación de
 *   la sesión (segunda barrera; la primera es el backend).
 * - Todo lo que no es GET exige mismo origen (CSRF).
 * - Las respuestas de error llegan como { error: { codigo, mensaje, reintentarEnS?,
 *   reiniciaEn? } } (p. ej. CUOTA_LLM_AGOTADA con la hora de reinicio).
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  BackendNoDisponibleError,
  borrarCookie,
  errorDesdeBackend,
  llamarBackend,
  respuestaError,
  sinBackend,
} from "@/lib/servidor/backend";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import {
  autorizarRuta,
  cuerpoRespuestaEsDeLaSesion,
  filtrarQuery,
  MAX_BYTES_ARCHIVO,
  MAX_BYTES_JSON,
} from "@/lib/servidor/proxy";
import { COOKIE_SESION, sesionDelToken } from "@/lib/servidor/sesion";

export const dynamic = "force-dynamic";

type Contexto = { params: Promise<{ ruta: string[] }> };

const NO_ENCONTRADO = { codigo: "NO_ENCONTRADO", mensaje: "Recurso no encontrado." };

async function manejar(req: NextRequest, { params }: Contexto): Promise<NextResponse> {
  const metodo = req.method.toUpperCase();
  if (metodo !== "GET" && !esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }

  const token = req.cookies.get(COOKIE_SESION)?.value;
  const sesion = sesionDelToken(token);
  if (!token || !sesion) {
    const res = respuestaError(401, { codigo: "SESION_EXPIRADA", mensaje: "Tu sesión terminó." });
    if (token) borrarCookie(res);
    return res;
  }

  const { ruta } = await params;
  const permiso = autorizarRuta(metodo, ruta, sesion.evaluacionId);
  if (!permiso.ok) return respuestaError(404, NO_ENCONTRADO);

  let cuerpo: BodyInit | null = null;
  let contentType: string | null = null;
  if (metodo !== "GET") {
    const largo = Number(req.headers.get("content-length") ?? "0");
    contentType = req.headers.get("content-type");
    if (permiso.archivo) {
      if (!contentType?.startsWith("multipart/form-data")) {
        return respuestaError(415, { codigo: "TIPO_NO_SOPORTADO", mensaje: "Adjunta el archivo como formulario." });
      }
      if (!largo || largo > MAX_BYTES_ARCHIVO) {
        return respuestaError(413, { codigo: "ARCHIVO_DEMASIADO_GRANDE", mensaje: "El archivo supera el máximo de 12 MB." });
      }
      cuerpo = req.body;
    } else {
      const texto = await req.text();
      if (texto.length > MAX_BYTES_JSON) {
        return respuestaError(413, { codigo: "CUERPO_DEMASIADO_GRANDE", mensaje: "Contenido demasiado grande." });
      }
      if (permiso.ruta === "respuestas/") {
        let json: unknown = null;
        try {
          json = JSON.parse(texto);
        } catch {
          /* lo rechaza el backend */
        }
        if (!cuerpoRespuestaEsDeLaSesion(json, sesion.evaluacionId)) return respuestaError(404, NO_ENCONTRADO);
      }
      cuerpo = texto || null;
      contentType = texto ? "application/json" : null;
    }
  }

  let res: Response;
  try {
    res = await llamarBackend(`/api/${permiso.ruta}${filtrarQuery(req.nextUrl.searchParams)}`, {
      metodo: metodo as "GET" | "POST" | "PUT" | "PATCH",
      cuerpo,
      contentType,
      token,
      // La IP solo la usa el backend para los límites por IP (evidencias, correos del informe)
      ip: permiso.conIp ? ipCliente(req.headers) : undefined,
      timeoutMs: permiso.timeoutMs ?? (permiso.archivo ? 60_000 : 15_000),
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }

  if (!res.ok) return errorDesdeBackend(res);
  if (permiso.binario) {
    // HU-12: el PDF pasa tal cual (res.text() corrompería los bytes)
    const tipo = res.headers.get("content-type") ?? "";
    if (!tipo.startsWith("application/pdf")) return respuestaError(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "El servidor no devolvió un PDF." });
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
  if (res.status === 204) return new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  return new NextResponse(await res.text(), {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("content-type") ?? "application/json",
      "Cache-Control": "no-store",
    },
  });
}

export const GET = manejar;
export const POST = manejar;
export const PUT = manejar;
export const PATCH = manejar;
