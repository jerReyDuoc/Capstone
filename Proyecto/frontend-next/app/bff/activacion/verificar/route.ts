/**
 * HU-27 · POST /bff/activacion/verificar  { token }  → ¿el enlace sigue válido? (no lo consume)
 *
 * Pasa por el BFF para que FastAPI reciba la IP real (límite de intentos por IP). El token
 * va en el cuerpo de un POST: nunca en la URL de una petición al servidor.
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
import { tokenActivacionValido } from "@/lib/activacion";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const datos = (await req.json().catch(() => null)) as { token?: unknown } | null;
  if (!tokenActivacionValido(datos?.token)) {
    return respuestaError(400, { codigo: "ENLACE_INVALIDO", mensaje: "El enlace no es válido." });
  }
  let res: Response;
  try {
    res = await llamarBackend("/api/auth/activacion/verificar", {
      metodo: "POST", json: { token: datos!.token }, ip: ipCliente(req.headers),
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (!res.ok) return errorDesdeBackend(res);
  return jsonSinCache(await res.json());
}
