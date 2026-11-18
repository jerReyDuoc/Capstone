/** Respuestas simuladas del espacio de la empresa (usuario definitivo) para las pruebas de navegador. */
import type { TablaFixtures } from "../simulacion";

const hoy = new Date();
const iso = (dias: number) => new Date(hoy.getTime() + dias * 86_400_000).toISOString().slice(0, 10);

export const ESPACIO_EMPRESA = {
  usuario: { nombre: "Persona de prueba", email: "persona@ejemplo.cl" },
  empresa: {
    id: 1,
    razon_social: "Empresa de Ejemplo SpA",
    rut: "76.123.456-7",
    rubro: "Servicios financieros",
    fecha_inicio_contrato: iso(-60),
    fecha_termino_contrato: iso(305),
    contrato_vigente: true,
    contrato: {
      estado: "activo",
      situacion: "vigente",
      fecha_inicio_contrato: iso(-60),
      fecha_termino_contrato: iso(305),
      servicio_habilitado: true,
      documentos_disponibles: true,
      en_plazo_de_gracia: false,
      documentos_disponibles_hasta: null,
      mensaje: "",
    },
  },
  evaluaciones: [
    { id: 9101, estado_progreso: "completada", completada: true, fecha_inicio: iso(-30), fecha_migracion: iso(-29), puntaje_general: 54.8 },
    { id: 9088, estado_progreso: "completada", completada: true, fecha_inicio: iso(-90), fecha_migracion: iso(-89), puntaje_general: 41.2 },
  ],
};

const cero = { Crítica: 0, Alta: 0, Media: 0, Baja: 0 };
const ceroRiesgo = { Bajo: 0, Medio: 0, Alto: 0, Crítico: 0 };

export const MAPA_VACIO = {
  mapa: { version: 0, fecha_actualizacion: null, iniciado: false, plantilla_inicial: null },
  elementos: [],
  flujos: [],
  resumen: {
    sistemas: 0, bases_datos: 0, terceros: 0, elementos: 0, flujos: 0, flujos_a_terceros: 0,
    transferencias_internacionales: 0, transferencias_sin_garantia: 0, elementos_con_sensibles: 0,
    flujos_con_sensibles: 0, elementos_con_nna: 0, fuera_de_chile: 0, proveedores_ia: 0,
    categorias_en_uso: 0, categorias_sensibles_en_uso: 0,
  },
  hallazgos: [],
  conteo_hallazgos: cero,
  completitud: { porcentaje: 0, pendientes: [] },
  limites: { max_elementos: 200, max_flujos: 400 },
  catalogo_version: "1",
};

const opcion = (codigo: string, nombre: string) => ({ codigo, nombre });

export const CATALOGO_MAPA = {
  version: "1",
  grupos_datos: ["Identificación"],
  categorias_datos: [{ codigo: "identificacion", nombre: "Identificación", grupo: "Identificación", descripcion: "Nombre, RUT", ejemplos: ["Nombre"], sensible: false }],
  categorias_titulares: [{ codigo: "clientes", nombre: "Clientes", descripcion: "", nna: false, posible_nna: false }],
  tipos: [opcion("sistema", "Sistema"), opcion("base_datos", "Base de datos"), opcion("tercero", "Tercero")],
  subtipos: { sistema: [], base_datos: [], tercero: [] },
  roles_tercero: [],
  garantias: [],
  frecuencias: [],
  medios: [],
  paises: [{ codigo: "CL", nombre: "Chile" }],
  pais_local: "CL",
};

export const CATALOGO_RAT = {
  version_textos: "1",
  revision_legal: { estado: "revisado", fecha: null },
  aviso: "",
  estados: [opcion("borrador", "Borrador"), opcion("en_revision", "En revisión"), opcion("vigente", "Vigente"), opcion("archivada", "Archivada")],
  bases_licitud: [],
  bases_sensibles: [],
  fuentes: [],
  unidades_plazo: [],
  inicios_plazo: [],
  max_plazo: {},
  grupos_medidas: [],
  medidas_seguridad: [],
  roles_empresa: [],
  campos: [],
  pasos: [
    { numero: 1, titulo: "Qué datos", descripcion: "" },
    { numero: 2, titulo: "Para qué", descripcion: "" },
  ],
};

export const REGISTRO_VACIO = {
  actividades: [],
  global: { porcentaje: 0, actividades: 0, completas: 0, por_estado: { borrador: 0, en_revision: 0, vigente: 0, archivada: 0 }, por_revisar: 0 },
  mapa: { version: 0, elementos: 0, flujos: 0, iniciado: false },
  limites: { max_actividades: 200 },
  riesgos: { por_nivel: ceroRiesgo, mayor_riesgo: 0, pia_recomendadas: 0, metodologia: "", metodologia_pia: "", referencia: "" },
  revision_interna: null,
};

export const CUMPLIMIENTO_VACIO = {
  mapa: { iniciado: false, version: 0, elementos: 0, flujos: 0, flujos_sin_actividad: 0 },
  registro: { activas: 0, vigentes: 0, completas: 0, en_revision: 0, borradores: 0, por_revisar: 0, completitud: 0, vigente_completo: false, faltantes: [] },
  riesgos: { referencia: "", metodologia: "", metodologia_pia: "", por_nivel: ceroRiesgo, mayor_riesgo: [], pia_recomendadas: 0, mapa_calor: [] },
  brechas: [],
  evidencia: { evaluacion_id: 9101, aplicable: false, faltantes: [], controles: [], por_mejorar: 0, puntaje_general: 54.8 },
  borradores: { pia: { recomendada: false, actividades: 0 }, aviso: { finalidades: 0 } },
};

const evidenciaBloqueada = {
  id_evidencia: 71, respuesta_id: 500, nombre_archivo: "politica_de_uso_de_ia_aprobada_por_el_directorio_2026.pdf",
  estado_validacion: "rejected", estado_declarado: "cumplido", estado_previo: "no_cumplido", estado_resultante: null,
  clasificacion_llm: null, confianza: null, justificacion_llm: null,
  errores_validacion: ["Bloqueo preventivo: posible prompt injection en la evidencia. La evidencia no fue enviada al LLM y quedó pendiente de revisión."],
  terminos_control: null, fecha_subida: iso(-1), fecha_procesada: iso(-1), en_proceso: false, mejoro: false, origen: "remediacion",
};

export const REMEDIACION = {
  evaluacion_id: 9101,
  puntaje_general: 54.8,
  puntaje_inicial: 54.8,
  evolucion: [],
  controles_mejorados: 0,
  dominios: [
    { dominio: "Gestión de Riesgos", puntaje: 46.2 },
    { dominio: "Gobernanza de IA", puntaje: 68.5 },
    { dominio: "Protección de Datos", puntaje: 38 },
    { dominio: "Uso Responsable", puntaje: 71.3 },
  ],
  controles: [
    {
      respuesta_id: 500, control_codigo: "DAT-001", codigo_brecha: "ERR-DAT-001", dominio: "Protección de Datos", estado: "no_cumplido",
      severidad: "Crítica", obligacion: "Validar y documentar el consentimiento antes de ingresar datos personales a un sistema de IA.",
      pregunta: "¿Tu organización valida y documenta el consentimiento antes de usar datos personales en sistemas de IA?",
      evidencia_esperada: "Procedimiento de consentimiento aprobado y registros de su aplicación.",
      recomendacion: "Definir un procedimiento de validación del consentimiento.", ruta: { id: 1, nombre: "Protección de Datos - Inicial" },
      formacion_completada: true, ultima_evidencia: evidenciaBloqueada, historial: [],
    },
    {
      respuesta_id: 501, control_codigo: "GOB-003", codigo_brecha: "ERR-GOB-003", dominio: "Gobernanza de IA", estado: "parcialmente_cumplido",
      severidad: "Alta", obligacion: "Mantener un inventario de herramientas de IA autorizadas.",
      pregunta: "¿Existe un inventario de las herramientas de IA que usa el personal?", evidencia_esperada: "Inventario actualizado.",
      recomendacion: null, ruta: null, formacion_completada: false, ultima_evidencia: null, historial: [],
    },
  ],
  tipos_admitidos: [".pdf", ".docx", ".txt"],
  max_mb: 10,
  evidencias_por_dia: 10,
};

export const FIXTURES_EMPRESA: TablaFixtures = [
  [/\/remediacion\/evaluaciones\/\d+$/, REMEDIACION],
  [/\/cliente\/empresa$/, ESPACIO_EMPRESA],
  [/\/mapa-datos\/catalogo$/, CATALOGO_MAPA],
  [/\/mapa-datos\/plantillas$/, { plantillas: [], version: "1" }],
  [/\/mapa-datos\/sugerencias$/, { evaluacion_id: 9101, sin_evaluacion: false, sugerencias: [], descartadas: 0 }],
  [/\/mapa-datos$/, MAPA_VACIO],
  [/\/registro-actividades\/catalogo$/, CATALOGO_RAT],
  [/\/registro-actividades\/cumplimiento$/, CUMPLIMIENTO_VACIO],
  [/\/registro-actividades$/, REGISTRO_VACIO],
  [/\/borradores\/plantillas$/, { plantillas: [], ia_habilitada: true, cuota: { usados: 0, limite: 5, restantes: 5, reinicia_en: "2026-12-01" }, max_caracteres_contenido: 20000, max_caracteres_instrucciones: 500, max_en_revision: 3 }],
  [/\/borradores$/, { items: [] }],
  [/\/arcop\/catalogo$/, { plazo_respuesta_dias: 30, plazo_prorroga_dias: 30, plazo_bloqueo_dias_habiles: 2, plazo_informacion_dias: 10 }],
  [/\/arcop\/solicitudes$/, { items: [], total: 0, page: 1, size: 100, pages: 0 }],
  [/\/formacion\/avance$/, () => undefined],
];
