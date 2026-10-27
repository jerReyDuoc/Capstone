/** HU-27/HU-28 · POST /bff/admin/logout — borra la cookie de sesión del administrador. */
import type { NextRequest } from "next/server";
import { jsonSinCache, respuestaError } from "@/lib/servidor/backend";
import { borrarCookieAdmin } from "@/lib/servidor/backendAdmin";
import { esMismoOrigen } from "@/lib/servidor/peticion";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const salida = jsonSinCache({ ok: true });
  borrarCookieAdmin(salida);
  return salida;
}
