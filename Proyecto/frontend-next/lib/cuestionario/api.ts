/**
 * HU-01 / HU-02 · Llamadas del cuestionario. Todas pasan por el BFF (/bff/api/*): el
 * navegador nunca ve el token y el proxy solo deja pasar la evaluación de la sesión.
 *
 * HU-29: el usuario definitivo responde sus reevaluaciones con el mismo cuestionario, pero
 * por su BFF (/bff/cliente/api/*). <Cuestionario base="/bff/cliente/api"> fija la base con
 * usarBaseCuestionario() antes de montar sus hijos (hay un solo cuestionario por página).
 * Los errores llegan como ErrorBff con { codigo, mensaje } (ver lib/encuesta/errores.ts).
 */
import { pedir } from "@/lib/encuesta/cliente";
import type {
  ControlAplicableApi,
  EstadoDeclarado,
  EstadoFiltroApi,
  EvidenciaApi,
  FiltroGuardadoApi,
  ProgresoApi,
  RespuestaDetalleApi,
  RespuestaGuardadaApi,
} from "./modelo";
import { normalizarJustificacion } from "./modelo";

export type BaseCuestionario = "/bff/api" | "/bff/cliente/api";
let BASE: BaseCuestionario = "/bff/api";

export function usarBaseCuestionario(base: BaseCuestionario): void {
  BASE = base;
}

export const baseCuestionario = (): BaseCuestionario => BASE;

const base = (id: number) => `${BASE}/evaluaciones/${id}`;

export const obtenerFiltro = (id: number) => pedir<EstadoFiltroApi>(`${base(id)}/filtro`);

export const guardarFiltro = (id: number, cuerpo: { respuestas: { codigo: string; respuesta: boolean }[] }) =>
  pedir<FiltroGuardadoApi>(`${base(id)}/filtro`, { method: "POST", json: cuerpo });

export const controlesAplicables = (id: number) => pedir<ControlAplicableApi[]>(`${base(id)}/controles-aplicables`);

export const obtenerProgreso = (id: number) => pedir<ProgresoApi>(`${base(id)}/progreso`);

/** Upsert por (evaluación, control): 201 la primera vez, 200 si ya existía. */
export const guardarRespuesta = (
  evaluacionId: number,
  idControl: number,
  estado: EstadoDeclarado,
  justificacion: string,
) =>
  pedir<RespuestaGuardadaApi>(`${BASE}/respuestas`, {
    method: "POST",
    json: {
      evaluacion_id: evaluacionId,
      matriz_control_id: idControl,
      estado_clasificacion: estado,
      justificacion: normalizarJustificacion(justificacion),
    },
  });

export const obtenerRespuesta = (idRespuesta: number) => pedir<RespuestaDetalleApi>(`${BASE}/respuestas/${idRespuesta}`);

export function subirEvidencia(idRespuesta: number, archivo: File) {
  const datos = new FormData();
  datos.append("file", archivo, archivo.name);
  return pedir<{ id_evidencia: number; nombre_archivo: string; estado_validacion: string; mensaje: string }>(
    `${BASE}/respuestas/${idRespuesta}/evidencias`,
    { method: "POST", body: datos },
  );
}

export const obtenerEvidencia = (idEvidencia: number) => pedir<EvidenciaApi>(`${BASE}/evidencias/${idEvidencia}`);

export const completarEvaluacion = (id: number) =>
  pedir<{ estado_progreso: string; controles_aplicables: number }>(`${base(id)}/completar`, { method: "POST" });
