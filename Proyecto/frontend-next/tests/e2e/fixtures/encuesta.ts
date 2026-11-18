/** Respuestas simuladas del cuestionario del encuestado (preguntas iniciales y controles). */
import type { TablaFixtures } from "../simulacion";

const PREGUNTAS = [
  ["F1", "¿Tu organización usa sistemas o herramientas de inteligencia artificial?"],
  ["F2", "¿Esos sistemas tratan datos sensibles (salud, biometría o perfiles de comportamiento)?"],
  ["F3", "¿Usan servicios de IA de terceros (por ejemplo, APIs en la nube)?"],
  ["F4", "¿Usan modelos de lenguaje generativo con datos de la organización?"],
  ["F5", "¿Algún sistema toma decisiones automatizadas que afectan a personas?"],
  ["F6", "¿Desarrollan o entrenan modelos propios?"],
  ["F7", "¿Usan agentes de IA que ejecutan acciones por su cuenta?"],
].map(([codigo, pregunta], i) => ({ id_pregunta: i + 1, codigo, orden: i + 1, pregunta, descripcion: null }));

const CONTROLES = [
  {
    id_control: 11,
    codigo_control: "GOB-001",
    framework_fuente: "ISO/IEC 42001",
    articulo_referencia: "5.2",
    tipo_fuente: "Norma técnica",
    obligacion: "Contar con una política de uso de IA aprobada por la dirección y comunicada al personal.",
    pregunta_evaluacion: "¿Tu organización tiene una política de uso de IA aprobada por la dirección y comunicada a todo el personal?",
    aplicabilidad: "Siempre",
    evidencia_esperada: "Política vigente con fecha de aprobación y registro de su difusión.",
    criticidad: "Alta",
    recomendacion: null,
    dominio: { id: 2, nombre_dominio: "Gobernanza de IA" },
  },
  {
    id_control: 12,
    codigo_control: "DAT-002",
    framework_fuente: "Ley 21.719",
    articulo_referencia: "Art. 14",
    tipo_fuente: "Ley",
    obligacion: "Informar a los titulares cuando sus datos se usan en sistemas de IA.",
    pregunta_evaluacion: "¿Informan a las personas cuando sus datos se usan en sistemas de IA?",
    aplicabilidad: "Siempre",
    evidencia_esperada: "Aviso de privacidad que menciona el uso de IA.",
    criticidad: "Media",
    recomendacion: null,
    dominio: { id: 3, nombre_dominio: "Protección de Datos" },
  },
];

const progreso = (etapa: "filtro" | "cuestionario") => ({
  evaluacion_id: 9101,
  estado_progreso: "en_progreso",
  cerrada: false,
  filtro_completado: etapa === "cuestionario",
  etapa,
  controles_aplicables: etapa === "cuestionario" ? CONTROLES.length : 0,
  controles_respondidos: 0,
  controles_pendientes: etapa === "cuestionario" ? CONTROLES.length : 0,
  porcentaje: 0,
  por_dimension: [],
  siguiente_control: etapa === "cuestionario" ? { id_control: 11, codigo_control: "GOB-001", dominio_id: 2, dominio: "Gobernanza de IA" } : null,
  pendientes: CONTROLES.map((c) => ({ id_control: c.id_control, codigo_control: c.codigo_control, dominio_id: c.dominio.id, dominio: c.dominio.nombre_dominio })),
  respondidos: [],
});

export function fixturesEncuesta(etapa: "filtro" | "cuestionario"): TablaFixtures {
  return [
    [/\/encuesta-publica\/limites$/, {
      evaluacion_id: 9101,
      evidencias: { usadas: 0, limite: 20, restantes: 20 },
      validaciones_ia: { usadas: 0, limite: 30, restantes: 30, reinicia_en: "2026-11-18T03:00:00Z" },
      servicio_ia_disponible: true,
    }],
    [/\/evaluaciones\/\d+\/progreso$/, progreso(etapa)],
    [/\/evaluaciones\/\d+\/filtro$/, {
      evaluacion_id: 9101,
      filtro_completado: etapa === "cuestionario",
      fecha_filtro: null,
      preguntas: PREGUNTAS,
      respuestas: etapa === "cuestionario" ? PREGUNTAS.map((p, i) => ({ id_respuesta_filtro: i + 1, pregunta_id: p.id_pregunta, respuesta: i < 2, fecha_respuesta: "2026-11-16" })) : [],
      controles_aplicables: etapa === "cuestionario" ? CONTROLES.length : 0,
    }],
    [/\/evaluaciones\/\d+\/controles-aplicables$/, CONTROLES],
  ];
}

export const FIXTURES_ENCUESTA: TablaFixtures = fixturesEncuesta("cuestionario");
