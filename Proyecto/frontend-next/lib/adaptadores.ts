import { CRITICIDADES, nivelDesdePuntaje } from "./madurez";
import { calcularSeveridad, contarPorSeveridad, PESO_SEVERIDAD } from "./severidad";
import type {
  BrechaCatalogoApi,
  BrechaVista,
  ComparativaApi,
  ControlApi,
  Criticidad,
  DominioVista,
  EstadoBrecha,
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
 * HU-11 · Análisis automático de brechas.
 *
 * Brecha = respuesta cuyo estado efectivo es no cumplido o parcialmente cumplido.
 * Se enriquece con el catálogo de brechas y, si falta, con el control de la matriz
 * (código, dominio, obligación, criticidad y recomendación). Las que no tienen
 * impacto conocido quedan "Sin clasificar": se cuentan igual para no esconder riesgo.
 *
 * Devuelve la lista ya priorizada y numerada (prioridad 1 = la más urgente).
 */
export function construirBrechas(
  respuestas: RespuestaApi[],
  catalogo: BrechaCatalogoApi[],
  controles: ControlApi[] = [],
  puntajesDominio: Map<string, number> = new Map(),
): BrechaVista[] {
  const porId = new Map(catalogo.map((b) => [b.id_brecha, b]));
  const ctrlPorId = new Map(controles.map((c) => [c.id_control, c]));

  return respuestas
    .filter((r) => ESTADOS_BRECHA.has(estadoEfectivo(r) ?? ""))
    .map<BrechaVista>((r) => {
      const ctrl = r.matriz_controles_id_control != null ? ctrlPorId.get(r.matriz_controles_id_control) : undefined;
      const idBrecha = r.catalogo_brechas_id_brecha;
      const cat = idBrecha != null ? porId.get(idBrecha) : undefined;
      const estado = estadoEfectivo(r) as EstadoBrecha;
      const { severidad, impacto } = calcularSeveridad(cat?.criticidad, estado, ctrl?.criticidad);
      const dominio = cat?.categoria ?? ctrl?.dominio?.nombre_dominio ?? "Sin dominio";
      return {
        respuestaId: r.id_respuesta,
        codigo: cat?.codigo_brecha ?? ctrl?.codigo_control ?? `RESP-${r.id_respuesta}`,
        dominio,
        descripcion:
          cat?.comportamiento_detectado ??
          ctrl?.obligacion ??
          "Control no cumplido sin brecha de catálogo asociada.",
        criticidad: impacto,
        severidad,
        prioridad: 0, // se numera después de ordenar
        estado,
        accion: cat?.accion_sistema ?? ctrl?.recomendacion ?? null,
        rutaFormativa: cat?.ruta_formativa?.nombre ?? null,
        controlId: r.matriz_controles_id_control,
        controlCodigo: ctrl?.codigo_control ?? null,
        puntajeDominio: puntajesDominio.get(dominio) ?? null,
      };
    })
    .sort(ordenarBrechas)
    .map((b, i) => ({ ...b, prioridad: i + 1 }));
}

const PESO_IMPACTO: Record<Criticidad, number> = { Alta: 0, Media: 1, Baja: 2, "Sin clasificar": 3 };

/**
 * Orden del listado priorizado:
 * 1. severidad (Crítica → Baja → Sin clasificar)
 * 2. no cumplidas antes que parciales
 * 3. mayor impacto del control
 * 4. dominio menos maduro primero (donde la empresa está más expuesta)
 * 5. código, para que el orden sea estable
 */
export function ordenarBrechas(a: BrechaVista, b: BrechaVista) {
  return (
    PESO_SEVERIDAD[a.severidad] - PESO_SEVERIDAD[b.severidad] ||
    (a.estado === b.estado ? 0 : a.estado === "no_cumplido" ? -1 : 1) ||
    PESO_IMPACTO[a.criticidad] - PESO_IMPACTO[b.criticidad] ||
    (a.puntajeDominio ?? 101) - (b.puntajeDominio ?? 101) ||
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
  controles?: ControlApi[];
}): PanelVista {
  const dominios = construirDominios(args.resumen, args.comparativa);
  const puntajes = new Map(dominios.map((d) => [d.nombre, d.puntaje]));
  const brechas = construirBrechas(args.respuestas, args.catalogo, args.controles ?? [], puntajes);
  return {
    evaluacionId: args.resumen.evaluacion_id,
    puntajeGeneral: args.resumen.puntaje_general,
    nivelGeneral: args.resumen.nivel_madurez_general ?? nivelDesdePuntaje(args.resumen.puntaje_general),
    controlesEvaluados: args.resumen.total_controles_evaluados,
    enRevision: args.respuestas.filter((r) => estadoEfectivo(r) === "requiere_revision").length,
    dominios,
    brechas,
    brechasPorCriticidad: contarPorCriticidad(brechas),
    brechasPorSeveridad: contarPorSeveridad(brechas),
    noCumplidos: brechas.filter((b) => b.estado === "no_cumplido").length,
    parciales: brechas.filter((b) => b.estado === "parcialmente_cumplido").length,
    tieneBenchmark: dominios.some((d) => d.promedioIndustria != null),
  };
}

const round = (n: number) => Math.round(n * 100) / 100;
