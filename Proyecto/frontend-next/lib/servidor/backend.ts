/**
 * HU-19 · Llamadas del servidor de Next (BFF) a FastAPI. Solo se importa desde
 * route handlers y Server Components (nunca desde un componente "use client").
 *
 * Reglas de seguridad:
 *   - El token va SOLO en el header Authorization hacia el backend; nunca en la URL.
 *   - No se registran headers ni cuerpos en los logs (tienen token, clave o datos).
 *   - X-BFF-Secret identifica al BFF ante la API; solo así la API confía en X-Cliente-IP.
 */
import { NextResponse } from "next/server";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";
import { parseErrorBackend } from "@/lib/encuesta/contratos";
import { COOKIE_SESION, opcionesCookie } from "./sesion";

const API_URL = (process.env.API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class BackendNoDisponibleError extends Error {}

export interface OpcionesBackend {
  metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: unknown;
  /** Cuerpo crudo (p. ej. el stream multipart de una evidencia). */
  cuerpo?: BodyInit | null;
  contentType?: string | null;
  token?: string;
  ip?: string;
  timeoutMs?: number;
}

export async function llamarBackend(ruta: string, o: OpcionesBackend = {}): Promise<Response> {
  const headers = new Headers({ Accept: "application/json" });
  const secreto = process.env.BFF_SHARED_SECRET;
  if (secreto) headers.set("X-BFF-Secret", secreto);
  if (o.ip) headers.set("X-Cliente-IP", o.ip);
  if (o.token) headers.set("Authorization", `Bearer ${o.token}`);

  let body: BodyInit | null | undefined = o.cuerpo;
  if (o.json !== undefined) {
    body = JSON.stringify(o.json);
    headers.set("Content-Type", "application/json");
  } else if (o.contentType) {
    headers.set("Content-Type", o.contentType);
  }

  const init: RequestInit & { duplex?: "half" } = {
    method: o.metodo ?? "GET",
    headers,
    body,
    cache: "no-store",
    redirect: "manual",
    signal: AbortSignal.timeout(o.timeoutMs ?? 15_000),
  };
  if (body instanceof ReadableStream) init.duplex = "half"; // requerido por fetch de Node para streams

  try {
    return await fetch(`${API_URL}${ruta}`, init);
  } catch (e) {
    // Solo el tipo de error: el mensaje podría incluir la URL o detalles internos
    console.error("[bff] backend no disponible:", (e as Error).name);
    throw new BackendNoDisponibleError();
  }
}

const SIN_CACHE = { "Cache-Control": "no-store", Pragma: "no-cache" } as const;

export function jsonSinCache(datos: unknown, status = 200): NextResponse {
  return NextResponse.json(datos, { status, headers: SIN_CACHE });
}

export function respuestaError(status: number, error: ErrorEncuesta): NextResponse {
  const res = jsonSinCache({ error }, status);
  if (error.reintentarEnS) res.headers.set("Retry-After", String(error.reintentarEnS));
  return res;
}

/** Convierte una respuesta de error del backend en { error } para el navegador. */
export async function errorDesdeBackend(res: Response): Promise<NextResponse> {
  let cuerpo: unknown = null;
  try {
    cuerpo = await res.json();
  } catch {
    /* sin cuerpo JSON */
  }
  const error = parseErrorBackend(res.status, cuerpo, res.headers.get("retry-after"));
  if (res.status === 401) error.codigo = "SESION_EXPIRADA";
  const salida = respuestaError(res.status, error);
  if (res.status === 401) borrarCookie(salida);
  return salida;
}

export function sinBackend(): NextResponse {
  return respuestaError(503, {
    codigo: "SIN_CONEXION",
    mensaje: "No pudimos conectar con el servidor.",
    reintentarEnS: 10,
  });
}

export function guardarCookie(res: NextResponse, token: string, expiraEnS: number): void {
  res.cookies.set(COOKIE_SESION, token, opcionesCookie(expiraEnS - Math.floor(Date.now() / 1000)));
}

export function borrarCookie(res: NextResponse): void {
  res.cookies.set(COOKIE_SESION, "", opcionesCookie(0));
}

/**
 * HU-28: cierra la sesión EN EL SERVIDOR (POST /api/auth/logout), así el token deja de
 * servir aunque alguien lo hubiera copiado. Es "mejor esfuerzo": si el backend no responde,
 * quien llama igual borra la cookie y el token vence solo a las AUTH_TOKEN_TTL_MIN.
 */
export async function cerrarSesionEnBackend(token: string | undefined, ip?: string): Promise<boolean> {
  if (!token) return false;
  try {
    const res = await llamarBackend("/api/auth/logout", { metodo: "POST", token, ip, timeoutMs: 5_000 });
    return res.status === 204 || res.status === 401; // 401: ya estaba cerrada o vencida
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return false;
    throw e;
  }
}
