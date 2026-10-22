/**
 * Datos de demostración (NEXT_PUBLIC_DEMO=1). Usan brechas reales del catálogo
 * sembrado (migración 2e398c9a9b2e) y pasan por el mismo adaptador que la API,
 * así el modo demo ejercita exactamente la misma lógica.
 */
import { construirPanel } from "./adaptadores";
import type {
  BrechaCatalogoApi,
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

  const comparativa: ComparativaApi = {
    evaluacion_id: id,
    rubro_id: 3,
    comparativas: filas.map(([dominio, puntaje, , prom]) => ({
      dominio,
      tu_puntaje: puntaje,
      tu_nivel: null,
      promedio_industria: prom,
      mediana_industria: prom,
      maximo_industria: 88,
      minimo_industria: 12,
      muestras: 27,
      diferencia_vs_promedio: Math.round((puntaje - prom) * 100) / 100,
    })),
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
