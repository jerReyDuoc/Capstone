/**
 * HU-32 · POST /bff/arcop/seguimiento — consulta pública del estado de una solicitud ARCOP.
 *
 * Navegador → { codigo: "ARC-XXXX-XXXX" }  ← 200 { codigo_seguimiento, tipo, estado, fechas… }
 *
 * - Sin sesión: sirve también después de una supresión aprobada (el titular ya no tiene
 *   clave ni cuenta, pero conserva su código).
 * - El código viaja en el cuerpo (POST), no en la URL, para que no quede en historiales ni
 *   en logs de proxies. El BFF lo valida y normaliza antes de llamar al backend
 *   (GET /api/arcop/seguimiento/{codigo}), que solo devuelve datos sin información personal.
 * - Ráfagas por IP en middleware.ts (40 bits de azar por código hacen inviable adivinarlos).
 */
import type { NextRequest } from "next/server";
import { normalizarCodigo } from "@/lib/arcop";
import { BackendNoDisponibleError, jsonSinCache, llamarBackend, respuestaError, sinBackend } from "@/lib/servidor/backend";
import { esMismoOrigen, ipCliente } from "@/lib/servidor/peticion";

export const dynamic = "force-dynamic";

const CAMPOS = [
  "codigo_seguimiento", "tipo", "estado", "fecha_creacion", "fecha_actualizacion",
  "fecha_limite_respuesta", "fecha_cierre", "prorrogada", "plazo_vencido",
] as const;

export async function POST(req: NextRequest) {
  if (!esMismoOrigen(req.headers)) {
    return respuestaError(403, { codigo: "ORIGEN_NO_PERMITIDO", mensaje: "Solicitud no permitida." });
  }
  const cuerpo = (await req.json().catch(() => null)) as { codigo?: unknown } | null;
  const codigo = typeof cuerpo?.codigo === "string" && cuerpo.codigo.length <= 40 ? normalizarCodigo(cuerpo.codigo) : "";
  if (!codigo) {
    return respuestaError(422, {
      codigo: "CODIGO_INVALIDO",
      mensaje: "Revisa el código: tiene el formato ARC-XXXX-XXXX.",
    });
  }

  let res: Response;
  try {
    res = await llamarBackend(`/api/arcop/seguimiento/${codigo}`, { ip: ipCliente(req.headers), timeoutMs: 10_000 });
  } catch (e) {
    if (e instanceof BackendNoDisponibleError) return sinBackend();
    throw e;
  }
  if (res.status === 404) {
    return respuestaError(404, {
      codigo: "NO_ENCONTRADA",
      mensaje: "No encontramos una solicitud con ese código. Revisa que esté bien escrito.",
    });
  }
  if (!res.ok) {
    return respuestaError(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "No pudimos consultar el estado. Inténtalo más tarde." });
  }
  const datos = (await res.json().catch(() => null)) as Record<string, unknown> | null;
  if (!datos || typeof datos.estado !== "string") {
    return respuestaError(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "Respuesta inesperada del servidor." });
  }
  // Solo los campos conocidos (lista blanca): nada más llega al navegador
  return jsonSinCache(Object.fromEntries(CAMPOS.map((c) => [c, datos[c] ?? null])));
}
