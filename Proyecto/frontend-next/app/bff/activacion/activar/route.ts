/**
 * HU-27 · POST /bff/activacion/activar  { token, password }  → el usuario definitivo define su contraseña.
 *
 * El enlace es de un solo uso: FastAPI lo marca como usado. La contraseña solo viaja en
 * el cuerpo y no se registra en ningún log. Los problemas de validación (CONTRASENA_DEBIL)
 * se devuelven tal cual para que el formulario los muestre.
 */
import type { NextRequest } from "next/server";
import {
  BackendNoDisponibleError,
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
  const datos = (await req.json().catch(() => null)) as { token?: unknown; password?: unknown } | null;
  if (!tokenActivacionValido(datos?.token)) {
    return respuestaError(400, { codigo: "ENLACE_INVALIDO", mensaje: "El enlace no es válido." });
  }
  if (typeof datos?.password !== "string" || !datos.password || datos.password.length > 200) {
    return respuestaError(422, { codigo: "DATOS_INVALIDOS", mensaje: "Escribe tu contraseña." });
  }
  let res: Response;
  try {
    res = await llamarBackend("/api/auth/activacion", {
      metodo: "POST", json: { token: datos.token, password: datos.password }, ip: ipCliente(req.headers),
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  const cuerpo = (await res.json().catch(() => null)) as { detail?: Record<string, unknown> } | null;
  if (res.ok) return jsonSinCache(cuerpo);
  const d = cuerpo?.detail ?? {};
  const problemas = Array.isArray(d.problemas) ? d.problemas.filter((p): p is string => typeof p === "string") : undefined;
  return jsonSinCache(
    {
      error: {
        codigo: typeof d.codigo === "string" ? d.codigo : `HTTP_${res.status}`,
        mensaje: typeof d.mensaje === "string" ? d.mensaje : "",
        ...(problemas ? { problemas } : {}),
      },
    },
    res.status,
  );
}
