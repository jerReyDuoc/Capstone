/**
 * Datos de demostración (NEXT_PUBLIC_DEMO=1). Usan brechas reales del catálogo
 * sembrado (migración 2e398c9a9b2e) y pasan por el mismo adaptador que la API,
 * así el modo demo ejercita exactamente la misma lógica.
 */
import { construirPanel } from "./adaptadores";
import { NIVELES_FORMATIVOS, nivelPorPuntaje } from "./planFormativo";
import { PESO_SEVERIDAD } from "./severidad";
import type {
  BrechaCatalogoApi,
  DimensionPlanApi,
  ModuloPlanApi,
  NivelFormativo,
  PlanFormativoApi,
  RutaPlanApi,
  ComparativaApi,
  ControlApi,
  EvaluacionApi,
  PanelVista,
  RespuestaApi,
  ResumenApi,
} from "./types";

export const DEMO_EVALUACIONES: EvaluacionApi[] = [
  { id: 9101, fecha_inicio: "2026-10-14", estado_progreso: "completada", usuario_temporal_id: 1 },
  { id: 9088, fecha_inicio: "2026-09-02", estado_progreso: "completada", usuario_temporal_id: 1 },
];

const CATALOGO: BrechaCatalogoApi[] = [
  ["ERR-DAT-001", "Protección de Datos", "Ingresar datos a la IA sin validar ni documentar el consentimiento previo.", "Alta", "Bloqueo preventivo / Alerta", "Protección de Datos - Inicial"],
  ["ERR-DAT-004", "Protección de Datos", "Omitir o rechazar injustificadamente una solicitud de eliminación (ARCOP).", "Alta", "Escalamiento a DPO", "Protección de Datos - Intermedio"],
  ["ERR-DAT-010", "Protección de Datos", "Lanzar un chatbot sin incluir el aviso de privacidad de uso de IA.", "Media", "Suspensión de interfaz", "Protección de Datos - Inicial"],
  ["ERR-GOB-003", "Gobernanza de IA", "Instalar o usar herramientas de 'Shadow AI' no contabilizadas por TI.", "Alta", "Bloqueo de URL/App", "Gobernanza de IA - Inicial"],
  ["ERR-GOB-006", "Gobernanza de IA", "Saltar controles de seguridad en el ciclo de vida de desarrollo de IA (SDLC).", "Media", "Bloqueo en pipeline CI/CD", "Gobernanza de IA - Intermedio"],
  ["ERR-RIE-002", "Gestión de Riesgos", "Utilizar salidas generadas por IA en informes sin verificar su precisión.", "Alta", "Marca de agua de revisión", "Gestión de Riesgos - Intermedio"],
  ["ERR-RIE-008", "Gestión de Riesgos", "Depender de una API de IA sin configurar un flujo manual de contingencia.", "Media", "Advertencia de arquitectura", "Gestión de Riesgos - Inicial"],
  ["ERR-RIE-011", "Gestión de Riesgos", "No registrar la versión del modelo usada en cada decisión automatizada.", "Baja", "Recordatorio de trazabilidad", "Gestión de Riesgos - Inicial"],
  ["ERR-SEG-004", "Uso Responsable", "Ejecutar código o consultas SQL generadas por IA sin sanitizarlas.", "Alta", "Bloqueo de compilación", "Uso Responsable - Avanzado"],
  ["ERR-SEG-010", "Uso Responsable", "Aprobar automáticamente una decisión crítica sin validación humana.", "Alta", "Reversión de la acción", "Uso Responsable - Inicial"],
  ["ERR-SEG-012", "Uso Responsable", "Publicar contenido generado por IA sin indicar su origen.", "Baja", "Etiqueta sugerida", "Uso Responsable - Inicial"],
].map(([codigo, categoria, comportamiento, criticidad, accion, ruta], i) => ({
  id_brecha: i + 1,
  codigo_brecha: codigo,
  categoria,
  comportamiento_detectado: comportamiento,
  criticidad,
  accion_sistema: accion,
  ruta_formativa: { id: i + 1, nombre: ruta },
}));

/** HU-11: control sin brecha de catálogo; el análisis toma su criticidad y código. */
const CONTROLES: ControlApi[] = [
  {
    id_control: 141,
    codigo_control: "GOB-007",
    obligacion: "Mantener un inventario actualizado de los sistemas de IA en uso y de sus responsables.",
    criticidad: "Media",
    recomendacion: "Levantar el inventario de sistemas de IA y asignar un responsable por sistema.",
    dominio: { id: 2, nombre_dominio: "Gobernanza de IA" },
  },
];

const PUNTAJES: Record<number, [string, number, number, number][]> = {
  // dominio, puntaje, controles, promedio industria
  9101: [
    ["Gestión de Riesgos", 46.2, 13, 52.4],
    ["Gobernanza de IA", 68.5, 12, 55.1],
    ["Protección de Datos", 38.0, 14, 49.8],
    ["Uso Responsable", 71.3, 11, 58.6],
  ],
  9088: [
    ["Gestión de Riesgos", 31.5, 13, 52.4],
    ["Gobernanza de IA", 52.0, 12, 55.1],
    ["Protección de Datos", 24.0, 14, 49.8],
    ["Uso Responsable", 60.7, 11, 58.6],
  ],
};

/** Brechas abiertas por evaluación: [id de catálogo, estado]. */
const BRECHAS: Record<number, [number, "no_cumplido" | "parcialmente_cumplido"][]> = {
  9101: [[1, "no_cumplido"], [2, "parcialmente_cumplido"], [3, "no_cumplido"], [4, "parcialmente_cumplido"], [6, "no_cumplido"], [7, "parcialmente_cumplido"], [8, "parcialmente_cumplido"], [9, "no_cumplido"], [11, "parcialmente_cumplido"]],
  9088: [[1, "no_cumplido"], [2, "no_cumplido"], [3, "no_cumplido"], [4, "no_cumplido"], [5, "no_cumplido"], [6, "no_cumplido"], [7, "parcialmente_cumplido"], [8, "no_cumplido"], [9, "no_cumplido"], [10, "no_cumplido"], [11, "parcialmente_cumplido"]],
};

export function panelDemo(evaluacionId: number): PanelVista {
  const id = PUNTAJES[evaluacionId] ? evaluacionId : DEMO_EVALUACIONES[0].id;
  const filas = PUNTAJES[id];
  const total = filas.reduce((s, f) => s + f[2], 0);
  const general = Math.round((filas.reduce((s, f) => s + f[1] * f[2], 0) / total) * 100) / 100;

  const resumen: ResumenApi = {
    evaluacion_id: id,
    puntaje_general: general,
    nivel_madurez_general: general <= 25 ? "inicial" : general <= 50 ? "en_desarrollo" : general <= 75 ? "gestionado" : "optimizado",
    total_controles_evaluados: total,
    dominios: filas.map(([dominio, puntaje, controles], i) => ({
      dominio_id: i + 1,
      dominio,
      puntaje,
      nivel_madurez: null, // el adaptador lo calcula
      total_controles_evaluados: controles,
    })),
  };

  // HU-10: cohorte de 27 empresas; la última dimensión tiene menos de 5 con puntaje y se suprime
  const suprimida = filas.length - 1;
  const promedioSector = 58;
  const comparativa: ComparativaApi = {
    evaluacion_id: id,
    rubro_id: 3,
    meta_puntaje: 75,
    meta_nivel: "gestionado",
    k_minimo: 5,
    muestras_minimas: 5,
    sector: {
      rubro_id: 3,
      rubro: "Servicios financieros",
      k_minimo: 5,
      cohorte_suficiente: true,
      empresas: 27,
      promedio: promedioSector,
      mediana: 57,
      percentil_25: 44,
      percentil_75: 71,
      tu_puntaje: general,
      diferencia: Math.round((general - promedioSector) * 10) / 10,
      posicion: general < 44 ? "bajo_cuartil_inferior" : general > 71 ? "sobre_cuartil_superior" : "franja_central",
      dimensiones_publicadas: filas.length - 1,
      dimensiones_suprimidas: 1,
      advertencia: {
        codigo: "COHORTE_PARCIAL",
        mensaje: `En 1 de ${filas.length} dimensiones hay menos de 5 empresas con puntaje, por eso esas comparaciones están ocultas.`,
      },
    },
    comparativas: filas.map(([dominio, puntaje, , prom], i): ComparativaApi["comparativas"][number] => {
      const ok = i !== suprimida;
      const p25 = Math.max(0, Math.round(prom - 13));
      const p75 = Math.min(100, Math.round(prom + 12));
      return {
        dominio_id: i + 1,
        dominio,
        tu_puntaje: puntaje,
        tu_nivel: null,
        promedio_industria: ok ? prom : null,
        mediana_industria: ok ? prom : null,
        percentil_25: ok ? p25 : null,
        percentil_75: ok ? p75 : null,
        cohorte_suficiente: ok,
        referencia_suficiente: ok,
        empresas: ok ? 27 : null,
        muestras: ok ? 27 : null,
        posicion: ok ? (puntaje < p25 ? "bajo_cuartil_inferior" : puntaje > p75 ? "sobre_cuartil_superior" : "franja_central") : null,
        diferencia_vs_promedio: ok ? Math.round((puntaje - prom) * 10) / 10 : null,
        meta: 75,
        diferencia_vs_meta: Math.round((puntaje - 75) * 100) / 100,
        cumple_meta: puntaje >= 75,
      };
    }),
  };

  const respuestas: RespuestaApi[] = [
    ...BRECHAS[id].map(([brecha, estado], i) => ({
      id_respuesta: 500 + i,
      estado_clasificacion: estado,
      estado_clasificacion_final: estado,
      fuente_clasificacion: "usuario",
      confianza_clasificacion: null,
      fecha_validacion: null,
      matriz_controles_id_control: 100 + brecha,
      catalogo_brechas_id_brecha: brecha,
    })),
    {
      id_respuesta: 900,
      estado_clasificacion: "requiere_revision",
      estado_clasificacion_final: null,
      fuente_clasificacion: "llm",
      confianza_clasificacion: 0.62,
      fecha_validacion: null,
      matriz_controles_id_control: 140,
      catalogo_brechas_id_brecha: null,
    },
    {
      id_respuesta: 901,
      estado_clasificacion: "no_cumplido",
      estado_clasificacion_final: "no_cumplido",
      fuente_clasificacion: "usuario",
      confianza_clasificacion: null,
      fecha_validacion: null,
      matriz_controles_id_control: 141,
      catalogo_brechas_id_brecha: null,
    },
  ];

  return construirPanel({ resumen, comparativa, respuestas, catalogo: CATALOGO, controles: CONTROLES });
}

/* ---------------------------------------------------------------- HU-12 (demo) */
const OBJETIVO_NIVEL: Record<NivelFormativo, string> = {
  Inicial: "Instalar las bases: que todo el personal conozca las obligaciones y aplique los controles mínimos.",
  Intermedio: "Aplicar los controles de forma consistente, con responsables, registros y evidencias que resistan una auditoría.",
  Avanzado: "Sostener la mejora continua: medir, auditar y resolver los casos complejos de la dimensión.",
};
const HORAS: Record<NivelFormativo, number> = { Inicial: 4, Intermedio: 8, Avanzado: 12 };

function rutaDemo(dominio: string, nivel: NivelFormativo, id: number): RutaPlanApi {
  return {
    id,
    nombre: `${dominio} - ${nivel}`,
    dominio,
    nivel,
    objetivo: `${nivel === "Inicial" ? "Conocer" : nivel === "Intermedio" ? "Aplicar" : "Liderar"} las prácticas de ${dominio.toLowerCase()} que exige la Ley 21.719 en el uso de IA.`,
    objetivos_especificos: [
      "Identificar las obligaciones que aplican al área.",
      "Aplicar el control en un caso real de la empresa.",
      "Registrar la evidencia de cumplimiento.",
    ],
    contenidos: ["Marco normativo", "Casos prácticos", "Evidencias y registros"],
    horas: HORAS[nivel],
    modalidad: nivel === "Inicial" ? "E-learning autoguiado" : "Taller práctico",
    publico_objetivo: nivel === "Inicial" ? "Todo el personal" : "Responsables de área",
  };
}

/** Plan del modo demo: misma regla que el backend (analisis.construir_plan), con el catálogo demo. */
export function planDemo(evaluacionId: number): PlanFormativoApi {
  const panel = panelDemo(evaluacionId);
  const dims = new Map<string, DimensionPlanApi>();
  panel.dominios.forEach((d) => {
    const nivel = nivelPorPuntaje(d.puntaje);
    dims.set(d.nombre, {
      dominio_id: d.id, dominio: d.nombre, puntaje: d.puntaje, nivel_madurez: d.nivel, nivel_asignado: nivel,
      objetivo_nivel: OBJETIVO_NIVEL[nivel], brechas: 0, horas: 0, modulos: [],
    });
  });
  const ids = new Map<string, number>();
  const idDe = (nombre: string) => ids.get(nombre) ?? (ids.set(nombre, ids.size + 1), ids.size);
  const modulos = new Map<string, [DimensionPlanApi, ModuloPlanApi]>();
  const sinRuta: PlanFormativoApi["brechas_sin_ruta"] = [];
  for (const b of panel.brechas) {
    const dimB = dims.get(b.dominio);
    if (dimB) dimB.brechas += 1;
    const cubierta = { codigo: b.codigo, control_codigo: b.controlCodigo, dominio: b.dominio, severidad: b.severidad, estado: b.estado, prioridad: b.prioridad };
    if (!b.rutaFormativa) {
      sinRuta.push(cubierta);
      continue;
    }
    const [dom, niv] = b.rutaFormativa.split(" - ") as [string, NivelFormativo];
    const dim = dims.get(dom) ?? dimB;
    if (!dim) continue;
    if (!modulos.has(b.rutaFormativa)) {
      modulos.set(b.rutaFormativa, [dim, { nivel: niv, motivo: "brechas", prioridad: b.severidad, ruta: rutaDemo(dom, niv, idDe(b.rutaFormativa)), brechas: [] }]);
    }
    const [, m] = modulos.get(b.rutaFormativa)!;
    m.brechas.push(cubierta);
    if (m.prioridad !== "Complementario" && PESO_SEVERIDAD[b.severidad] < PESO_SEVERIDAD[m.prioridad]) m.prioridad = b.severidad;
  }
  for (const dim of dims.values()) {
    const nombre = `${dim.dominio} - ${dim.nivel_asignado}`;
    if (!modulos.has(nombre)) {
      modulos.set(nombre, [dim, { nivel: dim.nivel_asignado, motivo: "nivel", prioridad: "Complementario", ruta: rutaDemo(dim.dominio, dim.nivel_asignado, idDe(nombre)), brechas: [] }]);
    }
  }
  for (const [dim, m] of modulos.values()) dim.modulos.push(m);
  const lista = [...dims.values()].sort((a, b) => a.dominio.localeCompare(b.dominio, "es"));
  for (const d of lista) {
    d.modulos.sort((a, b) => NIVELES_FORMATIVOS.indexOf(a.nivel) - NIVELES_FORMATIVOS.indexOf(b.nivel));
    d.horas = d.modulos.reduce((s, m) => s + (m.ruta.horas ?? 0), 0);
  }
  const mapeadas = panel.brechas.length - sinRuta.length;
  return {
    evaluacion_id: panel.evaluacionId,
    resumen: {
      dimensiones: lista.length,
      modulos: lista.reduce((s, d) => s + d.modulos.length, 0),
      horas: lista.reduce((s, d) => s + d.horas, 0),
      brechas_total: panel.brechas.length,
      brechas_mapeadas: mapeadas,
      cobertura_mapeo: panel.brechas.length ? Math.round((1000 * mapeadas) / panel.brechas.length) / 10 : 100,
    },
    brechas_sin_ruta: sinRuta,
    dimensiones: lista,
  };
}
