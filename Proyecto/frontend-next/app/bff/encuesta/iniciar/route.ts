/**
 * HU-19 · POST /bff/encuesta/iniciar
 *
 * Navegador → { rubroId, avisoVersion, avisoAceptado: true, captchaToken }
 * ← 201 { evaluacionId, clave, expiraEn }   + cookie httpOnly con el token
 *
 * El token NUNCA va en el cuerpo de la respuesta. La clave sí (una sola vez), porque
 * la persona debe guardarla para retomar; la respuesta es no-store.
 */
import type { NextRequest } from "next/server";
import { cuerpoIniciarBackend, parseIniciadaBackend, parseIniciarEntrada } from "@/lib/encuesta/contratos";
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

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  let datos: unknown;
  try {
    datos = await req.json();
  } catch {
    return respuestaError(400, { codigo: "DATOS_INVALIDOS", mensaje: "Cuerpo inválido." });
  }
  const entrada = parseIniciarEntrada(datos);
  if (!entrada.ok) {
    const codigo = entrada.error === "aviso no aceptado" ? "AVISO_NO_ACEPTADO" : "DATOS_INVALIDOS";
    return respuestaError(422, { codigo, mensaje: entrada.error });
  }
  if (!entrada.valor.captchaToken) {
    return respuestaError(400, { codigo: "CAPTCHA_PENDIENTE", mensaje: "Falta la verificación." });
  }

  let res: Response;
  try {
    res = await llamarBackend("/api/encuesta-publica/iniciar", {
      metodo: "POST",
      json: cuerpoIniciarBackend(entrada.valor),
      ip: ipCliente(req.headers),
      timeoutMs: 20_000,
    });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (!res.ok) return errorDesdeBackend(res);

  const iniciada = parseIniciadaBackend(await res.json().catch(() => null));
  if (!iniciada.ok) {
    console.error("[bff] respuesta inesperada de /iniciar:", iniciada.error); // solo el campo, nunca valores
    return respuestaError(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "Respuesta inesperada del servidor." });
  }

  const { evaluacion_id, clave_acceso, access_token, expira_en } = iniciada.valor;
  const salida = jsonSinCache({ evaluacionId: evaluacion_id, clave: clave_acceso, expiraEn: expira_en }, 201);
  guardarCookie(salida, access_token, expira_en);
  return salida;
}
