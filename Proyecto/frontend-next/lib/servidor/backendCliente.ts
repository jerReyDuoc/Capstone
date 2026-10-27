/**
 * HU-28 · Utilidades del BFF del usuario definitivo (solo route handlers del servidor).
 */
import { NextResponse } from "next/server";
import { parseErrorBackend } from "@/lib/encuesta/contratos";
import { respuestaError } from "./backend";
import { COOKIE_CLIENTE, opcionesCookieCliente } from "./sesionCliente";

export function guardarCookieCliente(res: NextResponse, token: string, expiraEnS: number): void {
  res.cookies.set(COOKIE_CLIENTE, token, opcionesCookieCliente(expiraEnS - Math.floor(Date.now() / 1000)));
}

export function borrarCookieCliente(res: NextResponse): void {
  res.cookies.set(COOKIE_CLIENTE, "", opcionesCookieCliente(0));
}

/** Error del backend → { error } para el navegador; un 401 además borra la cookie. */
export async function errorClienteDesdeBackend(res: Response): Promise<NextResponse> {
  let cuerpo: unknown = null;
  try {
    cuerpo = await res.json();
  } catch {
    /* sin cuerpo JSON */
  }
  const error = parseErrorBackend(res.status, cuerpo, res.headers.get("retry-after"));
  if (res.status === 401) error.codigo = "SESION_EXPIRADA";
  const salida = respuestaError(res.status, error);
  if (res.status === 401) borrarCookieCliente(salida);
  return salida;
}
