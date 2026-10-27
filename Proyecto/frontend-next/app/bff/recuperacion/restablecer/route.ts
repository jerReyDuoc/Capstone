/**
 * HU-28 · POST /bff/recuperacion/restablecer  { token, password }  → contraseña nueva.
 *
 * El enlace es de un solo uso y FastAPI cierra todas las sesiones abiertas de la cuenta.
 * La contraseña solo viaja en el cuerpo y no se registra. Los problemas de validación
 * (CONTRASENA_DEBIL) se devuelven tal cual para que el formulario los muestre. Por si quien
 * restablece tenía una sesión abierta en este navegador, se borran también sus cookies.
 */
import type { NextRequest } from "next/server";
import {
  BackendNoDisponibleError,
  jsonSinCache,
  llamarBackend,
  respuestaError,
  sinBackend,
} from "@/lib/servidor/backend";
import { borrarCookieAdmin } from "@/lib/servidor/backendAdmin";
import { borrarCookieCliente } from "@/lib/servidor/backendCliente";
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
    return respuestaError(422, { codigo: "DATOS_INVALIDOS", mensaje: "Escribe tu contraseña nueva." });
  }
  let res: Response;
  try {
    res = await llamarBackend("/api/auth/recuperacion/restablecer", {
      metodo: "POST", json: { token: datos.token, password: datos.password }, ip: ipCliente(req.headers),
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  const cuerpo = (await res.json().catch(() => null)) as Record<string, unknown> | null;
  if (res.ok) {
    const salida = jsonSinCache({ restablecido: true, tipo: cuerpo?.tipo === "admin" ? "admin" : "cliente" });
    if (cuerpo?.tipo === "admin") borrarCookieAdmin(salida);
    else borrarCookieCliente(salida);
    return salida;
  }
  const d = ((cuerpo?.detail ?? {}) as Record<string, unknown>) || {};
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
