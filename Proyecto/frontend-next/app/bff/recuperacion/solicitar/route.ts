/**
 * HU-28 · POST /bff/recuperacion/solicitar  { tipo: "cliente" | "admin", email }
 *
 * Pide el enlace para restablecer la contraseña. FastAPI responde SIEMPRE lo mismo (202)
 * exista o no la cuenta; aquí tampoco se distingue: el navegador recibe el mismo mensaje.
 */
import type { NextRequest } from "next/server";
import {
  BackendNoDisponibleError,
  errorDesdeBackend,
  jsonSinCache,
  llamarBackend,
  respuestaError,
  sinBackend,
} from "@/lib/servidor/backend";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { emailValido, tipoCuenta } from "@/lib/acceso";

export const dynamic = "force-dynamic";

const MENSAJE =
  "Si el correo corresponde a una cuenta activa, te enviamos un enlace para restablecer tu contraseña. " +
  "Revisa tu bandeja de entrada (y la carpeta de spam).";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const datos = (await req.json().catch(() => null)) as { tipo?: unknown; email?: unknown } | null;
  const email = typeof datos?.email === "string" ? datos.email.trim() : "";
  if (!emailValido(email)) {
    return respuestaError(422, { codigo: "DATOS_INVALIDOS", mensaje: "Escribe un correo válido." });
  }
  let res: Response;
  try {
    res = await llamarBackend("/api/auth/recuperacion", {
      metodo: "POST", json: { tipo: tipoCuenta(datos?.tipo), email }, ip: ipCliente(req.headers),
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (res.status === 202) return jsonSinCache({ mensaje: MENSAJE }, 202);
  return errorDesdeBackend(res); // 429 por IP o 503: no dicen nada de la cuenta
}
