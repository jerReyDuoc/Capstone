/**
 * HU-27 · Utilidades del BFF del panel interno (solo route handlers del servidor).
 */
import { NextResponse } from "next/server";
import { parseErrorBackend } from "@/lib/encuesta/contratos";
import { respuestaError } from "./backend";
import { COOKIE_ADMIN, opcionesCookieAdmin } from "./sesionAdmin";

export function guardarCookieAdmin(res: NextResponse, token: string, expiraEnS: number): void {
  res.cookies.set(COOKIE_ADMIN, token, opcionesCookieAdmin(expiraEnS - Math.floor(Date.now() / 1000)));
}

export function borrarCookieAdmin(res: NextResponse): void {
  res.cookies.set(COOKIE_ADMIN, "", opcionesCookieAdmin(0));
}

/**
 * Error del backend → { error } para el navegador. Conserva los campos extra que el panel
 * necesita mostrar (campo con error, solicitud que falló, problemas de validación).
 */
export async function errorAdminDesdeBackend(res: Response): Promise<NextResponse> {
  let cuerpo: unknown = null;
  try {
    cuerpo = await res.json();
  } catch {
    /* sin cuerpo JSON */
  }
  const error = parseErrorBackend(res.status, cuerpo, res.headers.get("retry-after"));
  const detalle = (cuerpo as { detail?: Record<string, unknown> } | null)?.detail;
  const extra: Record<string, unknown> = {};
  if (detalle && typeof detalle === "object" && !Array.isArray(detalle)) {
    for (const clave of ["campo", "solicitud_id", "estado_actual"]) {
      const v = detalle[clave];
      if (typeof v === "string" || typeof v === "number") extra[clave] = v;
    }
  }
  if (res.status === 401) error.codigo = "SESION_EXPIRADA";
  const salida = respuestaError(res.status, { ...error, ...extra });
  if (res.status === 401) borrarCookieAdmin(salida);
  return salida;
}
