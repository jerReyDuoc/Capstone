/**
 * HU-19 · POST /bff/encuesta/retomar
 *
 * Navegador → { evaluacionId, clave }  (desde cualquier dispositivo)
 * ← 200 { evaluacionId, expiraEn }     + cookie httpOnly con un token nuevo
 *
 * Usa el endpoint que ya existía: POST /api/auth/encuestado. La clave viaja solo en el
 * cuerpo (POST), nunca en la URL.
 */
import type { NextRequest } from "next/server";
import { parseLoginEncuestado, parseRetomarEntrada } from "@/lib/encuesta/contratos";
import {
  BackendNoDisponibleError,
  errorDesdeBackend,
  guardarCookie,
  jsonSinCache,
  llamarBackend,
  respuestaError,
  sinBackend,
} from "@/lib/servidor/backend";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";
import { leerToken } from "@/lib/servidor/sesion";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const entrada = parseRetomarEntrada(await req.json().catch(() => null));
  if (!entrada.ok) return respuestaError(422, { codigo: "DATOS_INVALIDOS", mensaje: entrada.error });

  let res: Response;
  try {
    res = await llamarBackend("/api/auth/encuestado", {
      metodo: "POST",
      json: { evaluacion_id: entrada.valor.evaluacionId, clave: entrada.valor.clave },
      ip: ipCliente(req.headers),
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (res.status === 401) {
    return respuestaError(401, { codigo: "CREDENCIALES_INVALIDAS", mensaje: "Número o clave incorrectos." });
  }
  if (!res.ok) return errorDesdeBackend(res);

  const login = parseLoginEncuestado(await res.json().catch(() => null));
  if (!login.ok) return respuestaError(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "Respuesta inesperada del servidor." });

  const expiraEn =
    leerToken(login.valor.access_token)?.exp ?? Math.floor(Date.now() / 1000) + login.valor.expira_en_min * 60;
  const salida = jsonSinCache({ evaluacionId: login.valor.usuario_id, expiraEn });
  guardarCookie(salida, login.valor.access_token, expiraEn);
  return salida;
}
