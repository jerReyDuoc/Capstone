import { construirPanel } from "./adaptadores";
import { DEMO_EVALUACIONES, panelDemo, planDemo } from "./demo";
import { filtrosAParams, type FiltrosBrechas } from "./filtrosBrechas";
import type {
  BrechaCatalogoApi,
  ComparativaApi,
  ControlApi,
  EvaluacionApi,
  Paginado,
  PanelVista,
  PlanFormativoApi,
  RespuestaApi,
  ResumenApi,
} from "./types";

export const MODO_DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

/**
 * De dónde salen los datos del panel:
 *   "/api"     → equipo interno (rewrite de Next a FastAPI, como hasta ahora)
 *   "/bff/cliente/api" → usuario definitivo de una empresa cliente (HU-28): ve las evaluaciones
 *                migradas a su empresa; el BFF agrega el token de su cookie httpOnly.
 *   "/bff/api" → encuestado de la landing (HU-19): su evaluación es pública y la API exige
 *                su token, que vive en la cookie httpOnly; el BFF lo agrega y solo deja
 *                pasar SU evaluación.
 */
export type BaseApi = "/api" | "/bff/api" | "/bff/cliente/api";

/** Error con un mensaje apto para mostrar al usuario y el código HTTP. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public codigo?: string,
  ) {
    super(message);
  }
}

async function getJson<T>(ruta: string, signal?: AbortSignal): Promise<T> {
  const res = await pedir(ruta, { headers: { Accept: "application/json" }, signal });
  return res.json() as Promise<T>;
}

/** fetch con los mensajes de error de la API (FastAPI { detail } o BFF { error }). */
async function pedir(ruta: string, init: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(ruta, { cache: "no-store", ...init });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("No pudimos conectar con el servidor. Revisa que la API esté en línea.", 0);
  }
  if (!res.ok) {
    let detalle: unknown;
    try {
      const cuerpo = await res.json();
      // FastAPI: { detail }; BFF: { error: { codigo, mensaje } }
      detalle = cuerpo?.detail ?? cuerpo?.error;
    } catch {
      /* cuerpo vacío */
    }
    const msg =
      typeof detalle === "string"
        ? detalle
        : (detalle as { mensaje?: string } | undefined)?.mensaje ?? `Error ${res.status} al consultar ${ruta}`;
    throw new ApiError(msg, res.status, (detalle as { codigo?: string } | undefined)?.codigo);
  }
  return res;
}

/** Recorre todas las páginas (size máx. 100 en el backend). */
async function getTodasLasPaginas<T>(base: string, signal?: AbortSignal): Promise<T[]> {
  const sep = base.includes("?") ? "&" : "?";
  const primera = await getJson<Paginado<T>>(`${base}${sep}page=1&size=100`, signal);
  const resto = await Promise.all(
    Array.from({ length: Math.max(0, primera.pages - 1) }, (_, i) =>
      getJson<Paginado<T>>(`${base}${sep}page=${i + 2}&size=100`, signal),
    ),
  );
  return [primera, ...resto].flatMap((p) => p.items);
}

export async function listarEvaluaciones(signal?: AbortSignal, base: BaseApi = "/api"): Promise<EvaluacionApi[]> {
  if (MODO_DEMO) return DEMO_EVALUACIONES;
  const pagina = await getJson<Paginado<EvaluacionApi>>(`${base}/evaluaciones?page=1&size=100`, signal);
  return pagina.items;
}

/** HU-28: ¿hay una sesión de usuario definitivo (cliente) en este navegador? */
export async function sesionCliente(signal?: AbortSignal): Promise<boolean> {
  if (MODO_DEMO) return false;
  try {
    const s = await getJson<{ activa: boolean }>("/bff/cliente/sesion", signal);
    return s.activa === true;
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    return false;
  }
}

/** Sesión del encuestado (cookie httpOnly) o null si no hay / no se pudo consultar. */
export async function sesionEncuestado(signal?: AbortSignal): Promise<number | null> {
  if (MODO_DEMO) return null;
  try {
    const s = await getJson<{ activa: boolean; evaluacionId?: number }>("/bff/encuesta/sesion", signal);
    return s.activa && typeof s.evaluacionId === "number" ? s.evaluacionId : null;
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    return null; // sin BFF o sin backend: el panel sigue en modo interno
  }
}

/** La evaluación del encuestado (una sola: la de su sesión). */
export async function evaluacionDelEncuestado(evaluacionId: number, signal?: AbortSignal): Promise<EvaluacionApi> {
  return getJson<EvaluacionApi>(`/bff/api/evaluaciones/${evaluacionId}`, signal);
}

export async function cargarPanel(evaluacionId: number, signal?: AbortSignal, base: BaseApi = "/api"): Promise<PanelVista> {
  if (MODO_DEMO) return panelDemo(evaluacionId);

  const [resumen, respuestas, catalogo, comparativa, controles] = await Promise.all([
    getJson<ResumenApi>(`${base}/evaluaciones/${evaluacionId}/resumen`, signal),
    getTodasLasPaginas<RespuestaApi>(`${base}/evaluaciones/${evaluacionId}/respuestas`, signal),
    getJson<BrechaCatalogoApi[]>(`${base}/brechas`, signal),
    // Sin rubro o sin benchmark el panel sigue funcionando: solo se oculta la serie "industria".
    getJson<ComparativaApi>(`${base}/evaluaciones/${evaluacionId}/comparativa`, signal).catch((e) => {
      if ((e as Error).name === "AbortError") throw e;
      return null;
    }),
    // HU-11: el control aporta código, dominio y criticidad cuando la respuesta no trae brecha
    // de catálogo. Si falla, el análisis sigue con el catálogo solo.
    getJson<ControlApi[]>(`${base}/controles`, signal).catch((e) => {
      if ((e as Error).name === "AbortError") throw e;
      return [] as ControlApi[];
    }),
  ]);

  return construirPanel({ resumen, comparativa, respuestas, catalogo, controles });
}

/* ------------------------------------------------------------------
 * HU-12 · Plan formativo e informe (PDF descargable y por correo)
 * ------------------------------------------------------------------ */

export async function cargarPlanFormativo(
  evaluacionId: number,
  signal?: AbortSignal,
  base: BaseApi = "/api",
): Promise<PlanFormativoApi> {
  if (MODO_DEMO) return planDemo(evaluacionId);
  return getJson<PlanFormativoApi>(`${base}/evaluaciones/${evaluacionId}/plan-formativo`, signal);
}

const consulta = (filtros?: FiltrosBrechas) => {
  const q = new URLSearchParams(filtros ? filtrosAParams(filtros) : {}).toString();
  return q ? `?${q}` : "";
};

/** Nombre que propone el servidor en Content-Disposition, o uno de respaldo. */
export function nombreDesdeDisposicion(cabecera: string | null, respaldo: string): string {
  const m = /filename="?([^";]+)"?/i.exec(cabecera ?? "");
  const nombre = m?.[1]?.trim();
  return nombre && /^[\w.-]+\.pdf$/i.test(nombre) ? nombre : respaldo;
}

/**
 * Descarga el informe en PDF generado por el servidor (el mismo que se envía por correo).
 * Con filtros, el listado de brechas del PDF es el filtrado.
 */
export async function descargarInformePdf(
  evaluacionId: number,
  filtros?: FiltrosBrechas,
  base: BaseApi = "/api",
): Promise<{ blob: Blob; nombre: string }> {
  const res = await pedir(`${base}/evaluaciones/${evaluacionId}/informe/pdf${consulta(filtros)}`, {
    headers: { Accept: "application/pdf" },
  });
  const blob = await res.blob();
  return { blob, nombre: nombreDesdeDisposicion(res.headers.get("content-disposition"), `informe_evaluacion-${evaluacionId}.pdf`) };
}

export interface EnvioInforme {
  enviado: boolean;
  /** Correo enmascarado (j***z@empresa.cl). */
  destino: string;
  /** "archivo" = entorno de desarrollo: el correo se guardó en el servidor, no salió. */
  modo: "smtp" | "archivo";
}

export async function enviarInformePorCorreo(
  evaluacionId: number,
  datos: { email?: string; recordar?: boolean; filtros?: FiltrosBrechas },
  base: BaseApi = "/api",
): Promise<EnvioInforme> {
  if (MODO_DEMO) throw new ApiError("En modo demo no se envían correos. Conecta el backend para probarlo.", 0);
  const cuerpo = {
    email: datos.email?.trim() || null,
    recordar: Boolean(datos.recordar),
    ...(datos.filtros ? filtrosAParams(datos.filtros) : {}),
  };
  const res = await pedir(`${base}/evaluaciones/${evaluacionId}/informe/enviar`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  return res.json() as Promise<EnvioInforme>;
}
