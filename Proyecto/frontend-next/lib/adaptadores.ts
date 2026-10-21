import { CRITICIDADES, nivelDesdePuntaje, normalizarCriticidad } from "./madurez";
import type {
  BrechaCatalogoApi,
  BrechaVista,
  ComparativaApi,
  Criticidad,
  DominioVista,
  PanelVista,
  RespuestaApi,
  ResumenApi,
} from "./types";

const ESTADOS_BRECHA = new Set(["no_cumplido", "parcialmente_cumplido"]);

/** Estado efectivo: el final (post revisión LLM/humana) manda sobre el original. */
export function estadoEfectivo(r: RespuestaApi) {
  return r.estado_clasificacion_final ?? r.estado_clasificacion;
}

/**
 * Brecha = respuesta no cumplida o parcialmente cumplida que el backend
 * asoció a una entrada del catálogo de brechas. Las respuestas sin brecha
 * asociada se cuentan igual (como "Sin clasificar") para no esconder riesgo.
 */
export function construirBrechas(
  respuestas: RespuestaApi[],
  catalogo: BrechaCatalogoApi[],
): BrechaVista[] {
  const porId = new Map(catalogo.map((b) => [b.id_brecha, b]));

  return respuestas
    .filter((r) => ESTADOS_BRECHA.has(estadoEfectivo(r) ?? ""))
    .map<BrechaVista>((r) => {
      const cat = r.catalogo_brechas_id_brecha != null ? porId.get(r.catalogo_brechas_id_brecha) : undefined;
      return {
        respuestaId: r.id_respuesta,
        codigo: cat?.codigo_brecha ?? `RESP-${r.id_respuesta}`,
        dominio: cat?.categoria ?? "Sin dominio",
        descripcion: cat?.comportamiento_detectado ?? "Control no cumplido sin brecha de catálogo asociada.",
        criticidad: normalizarCriticidad(cat?.criticidad),
        estado: estadoEfectivo(r) as BrechaVista["estado"],
        accion: cat?.accion_sistema ?? null,
        rutaFormativa: cat?.ruta_formativa?.nombre ?? null,
        controlId: r.matriz_controles_id_control,
      };
    })
    .sort(ordenarBrechas);
}

const PESO: Record<Criticidad, number> = { Alta: 0, Media: 1, Baja: 2, "Sin clasificar": 3 };

export function ordenarBrechas(a: BrechaVista, b: BrechaVista) {
  return (
    PESO[a.criticidad] - PESO[b.criticidad] ||
    (a.estado === b.estado ? 0 : a.estado === "no_cumplido" ? -1 : 1) ||
    a.codigo.localeCompare(b.codigo, "es")
  );
}

export function contarPorCriticidad(brechas: BrechaVista[]): Record<Criticidad, number> {
  const base = Object.fromEntries(CRITICIDADES.map((c) => [c, 0])) as Record<Criticidad, number>;
  for (const b of brechas) base[b.criticidad] += 1;
  return base;
}

export function construirDominios(resumen: ResumenApi, comparativa: ComparativaApi | null): DominioVista[] {
  const bench = new Map((comparativa?.comparativas ?? []).map((c) => [c.dominio, c]));
  return resumen.dominios
    .map<DominioVista>((d) => {
      const puntaje = d.puntaje ?? 0;
      const c = bench.get(d.dominio);
      const prom = c?.promedio_industria ?? null;
      return {
        id: d.dominio_id,
        nombre: d.dominio,
        puntaje,
        nivel: d.nivel_madurez ?? nivelDesdePuntaje(puntaje),
        controles: d.total_controles_evaluados ?? 0,
        promedioIndustria: prom,
        diferencia: c?.diferencia_vs_promedio ?? (prom != null ? round(puntaje - prom) : null),
        muestras: c?.muestras ?? 0,
      };
    })
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
}

export function construirPanel(args: {
  resumen: ResumenApi;
  comparativa: ComparativaApi | null;
  respuestas: RespuestaApi[];
  catalogo: BrechaCatalogoApi[];
}): PanelVista {
  const dominios = construirDominios(args.resumen, args.comparativa);
  const brechas = construirBrechas(args.respuestas, args.catalogo);
  return {
    evaluacionId: args.resumen.evaluacion_id,
    puntajeGeneral: args.resumen.puntaje_general,
    nivelGeneral: args.resumen.nivel_madurez_general ?? nivelDesdePuntaje(args.resumen.puntaje_general),
    controlesEvaluados: args.resumen.total_controles_evaluados,
    enRevision: args.respuestas.filter((r) => estadoEfectivo(r) === "requiere_revision").length,
    dominios,
    brechas,
    brechasPorCriticidad: contarPorCriticidad(brechas),
    tieneBenchmark: dominios.some((d) => d.promedioIndustria != null),
  };
}

const round = (n: number) => Math.round(n * 100) / 100;
