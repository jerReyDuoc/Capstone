import { construirPanel } from "./adaptadores";
import { DEMO_EVALUACIONES, panelDemo } from "./demo";
import type {
  BrechaCatalogoApi,
  ComparativaApi,
  EvaluacionApi,
  Paginado,
  PanelVista,
  RespuestaApi,
  ResumenApi,
} from "./types";

export const MODO_DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

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
  let res: Response;
  try {
    res = await fetch(ruta, { headers: { Accept: "application/json" }, signal, cache: "no-store" });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("No pudimos conectar con el servidor. Revisa que la API esté en línea.", 0);
  }
  if (!res.ok) {
    let detalle: unknown;
    try {
      detalle = (await res.json())?.detail;
    } catch {
      /* cuerpo vacío */
    }
    const msg =
      typeof detalle === "string"
        ? detalle
        : (detalle as { mensaje?: string } | undefined)?.mensaje ?? `Error ${res.status} al consultar ${ruta}`;
    throw new ApiError(msg, res.status, (detalle as { codigo?: string } | undefined)?.codigo);
  }
  return res.json() as Promise<T>;
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

export async function listarEvaluaciones(signal?: AbortSignal): Promise<EvaluacionApi[]> {
  if (MODO_DEMO) return DEMO_EVALUACIONES;
  const pagina = await getJson<Paginado<EvaluacionApi>>("/api/evaluaciones?page=1&size=100", signal);
  return pagina.items;
}

export async function cargarPanel(evaluacionId: number, signal?: AbortSignal): Promise<PanelVista> {
  if (MODO_DEMO) return panelDemo(evaluacionId);

  const [resumen, respuestas, catalogo, comparativa] = await Promise.all([
    getJson<ResumenApi>(`/api/evaluaciones/${evaluacionId}/resumen`, signal),
    getTodasLasPaginas<RespuestaApi>(`/api/evaluaciones/${evaluacionId}/respuestas`, signal),
    getJson<BrechaCatalogoApi[]>("/api/brechas", signal),
    // Sin rubro o sin benchmark el panel sigue funcionando: solo se oculta la serie "industria".
    getJson<ComparativaApi>(`/api/evaluaciones/${evaluacionId}/comparativa`, signal).catch((e) => {
      if ((e as Error).name === "AbortError") throw e;
      return null;
    }),
  ]);

  return construirPanel({ resumen, comparativa, respuestas, catalogo });
}
