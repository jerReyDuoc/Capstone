/**
 * HU-19 · PATCH /bff/encuesta/email   { email: string | null }  → 204
 *
 * Email OPCIONAL (recibir el informe / retomar). Se ofrece DESPUÉS de crear la
 * evaluación: nunca es un requisito para empezar.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { parseEmailEntrada } from "@/lib/encuesta/contratos";
import { BackendNoDisponibleError, errorDesdeBackend, llamarBackend, respuestaError, sinBackend } from "@/lib/servidor/backend";
import { esMismoOrigen } from "@/lib/servidor/peticion";
import { COOKIE_SESION, sesionDelToken } from "@/lib/servidor/sesion";

export const dynamic = "force-dynamic";

export async function PATCH(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const token = req.cookies.get(COOKIE_SESION)?.value;
  if (!token || !sesionDelToken(token)) {
    return respuestaError(401, { codigo: "SESION_EXPIRADA", mensaje: "Tu sesión terminó." });
  }
  const entrada = parseEmailEntrada(await req.json().catch(() => null));
  if (!entrada.ok) return respuestaError(422, { codigo: "EMAIL_INVALIDO", mensaje: entrada.error });

  let res: Response;
  try {
    res = await llamarBackend("/api/encuesta-publica/email", { metodo: "PATCH", json: entrada.valor, token });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (!res.ok) return errorDesdeBackend(res);
  return new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
}
