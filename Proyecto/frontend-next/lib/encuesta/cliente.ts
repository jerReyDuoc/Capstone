/**
 * HU-19 · Llamadas del NAVEGADOR al BFF (/bff/*). Nunca a /api/* directo: el token
 * vive en una cookie httpOnly que solo el BFF puede leer.
 *
 * Reintentos: solo en GET y solo ante errores de red o 502/503/504 (con espera
 * creciente y respetando Retry-After). Nunca se reintenta un 429 de cuota o de
 * límites: ahí reintentar no sirve y solo gasta intentos.
 */
import type { ErrorEncuesta } from "./contratos";

export class ErrorBff extends Error {
  constructor(
    public status: number,
    public info: ErrorEncuesta,
  ) {
    super(info.mensaje || info.codigo);
  }
}

const REINTENTABLES = new Set([502, 503, 504]);
const esperar = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function leerError(res: Response): Promise<ErrorEncuesta> {
  try {
    const cuerpo = (await res.json()) as { error?: ErrorEncuesta };
    if (cuerpo?.error?.codigo) return cuerpo.error;
  } catch {
    /* sin cuerpo */
  }
  const retry = res.headers.get("retry-after");
  return { codigo: `HTTP_${res.status}`, mensaje: "", reintentarEnS: retry ? Number(retry) || undefined : undefined };
}

export async function pedir<T>(
  url: string,
  init: RequestInit & { json?: unknown } = {},
  { reintentos = 2 }: { reintentos?: number } = {},
): Promise<T> {
  const metodo = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  let body = init.body;
  if (init.json !== undefined) {
    body = JSON.stringify(init.json);
    headers.set("Content-Type", "application/json");
  }
  const intentos = metodo === "GET" ? reintentos + 1 : 1;

  for (let i = 0; i < intentos; i++) {
    let res: Response;
    try {
      res = await fetch(url, { ...init, method: metodo, headers, body, credentials: "same-origin", cache: "no-store" });
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
      if (i < intentos - 1) {
        await esperar(500 * 2 ** i);
        continue;
      }
      throw new ErrorBff(0, { codigo: "SIN_CONEXION", mensaje: "" });
    }
    if (res.ok) {
      if (res.status === 204) return undefined as T;
      return (await res.json()) as T;
    }
    if (REINTENTABLES.has(res.status) && i < intentos - 1) {
      const retry = Number(res.headers.get("retry-after"));
      await esperar(Number.isFinite(retry) && retry > 0 ? Math.min(retry, 10) * 1000 : 500 * 2 ** i);
      continue;
    }
    throw new ErrorBff(res.status, await leerError(res));
  }
  throw new ErrorBff(0, { codigo: "SIN_CONEXION", mensaje: "" });
}

/** Normaliza cualquier error a ErrorEncuesta para mostrarlo con mensajeDeError(). */
export function comoErrorEncuesta(e: unknown): ErrorEncuesta {
  if (e instanceof ErrorBff) return e.info;
  return { codigo: "DESCONOCIDO", mensaje: "" };
}
