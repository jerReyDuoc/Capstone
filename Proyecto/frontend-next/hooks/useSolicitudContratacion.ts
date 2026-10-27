"use client";

/**
 * HU-31 · Estado de la solicitud de contratación del encuestado (para el CTA de los
 * resultados y la página /panel/contratar). Solo en modo "encuestado": el equipo interno
 * no pide contratar.
 */
import { useCallback, useEffect, useState } from "react";
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import { parseConsentimientos, parseSolicitud, type Consentimientos, type SolicitudPublica } from "@/lib/contratacion";

const BASE = "/bff/api/contratacion";

export async function obtenerSolicitud(evaluacionId: number, signal?: AbortSignal): Promise<SolicitudPublica | null> {
  try {
    return parseSolicitud(await pedir<unknown>(`${BASE}/evaluaciones/${evaluacionId}/solicitud`, { signal }));
  } catch (e) {
    if (e instanceof ErrorBff && e.status === 404) return null; // aún no la envía
    throw e;
  }
}

export async function obtenerConsentimientos(signal?: AbortSignal): Promise<Consentimientos> {
  const textos = parseConsentimientos(await pedir<unknown>(`${BASE}/consentimiento`, { signal }));
  if (!textos) throw new ErrorBff(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "" });
  return textos;
}

export async function enviarSolicitud(cuerpo: unknown): Promise<SolicitudPublica> {
  const s = parseSolicitud(await pedir<unknown>(`${BASE}/solicitudes`, { method: "POST", json: cuerpo }));
  if (!s) throw new ErrorBff(502, { codigo: "RESPUESTA_INVALIDA", mensaje: "" });
  return s;
}

export type EstadoSolicitud =
  | { tipo: "cargando" }
  | { tipo: "sin-solicitud" }
  | { tipo: "enviada"; solicitud: SolicitudPublica }
  | { tipo: "error" };

export function useSolicitudContratacion(evaluacionId: number | null, activo: boolean) {
  const [estado, setEstado] = useState<EstadoSolicitud>({ tipo: "cargando" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!activo || evaluacionId == null) return;
    const ctrl = new AbortController();
    setEstado({ tipo: "cargando" });
    obtenerSolicitud(evaluacionId, ctrl.signal)
      .then((s) => setEstado(s ? { tipo: "enviada", solicitud: s } : { tipo: "sin-solicitud" }))
      .catch((e) => {
        if ((e as Error).name !== "AbortError") setEstado({ tipo: "error" });
      });
    return () => ctrl.abort();
  }, [evaluacionId, activo, version]);

  const marcarEnviada = useCallback((solicitud: SolicitudPublica) => setEstado({ tipo: "enviada", solicitud }), []);
  const recargar = useCallback(() => setVersion((v) => v + 1), []);
  return { estado, marcarEnviada, recargar };
}
