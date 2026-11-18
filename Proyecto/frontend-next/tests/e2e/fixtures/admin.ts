/** Respuestas simuladas del panel interno (administrador) para las pruebas de navegador. */
import type { TablaFixtures } from "../simulacion";

const ahora = new Date();
const iso = (dias: number) => new Date(ahora.getTime() + dias * 86_400_000).toISOString();
const pagina = <T,>(items: T[]) => ({ items, total: items.length, page: 1, size: 100, pages: 1 });

const consentimiento = { aceptado: true, version: "1.0", fecha: iso(-3) };

const SOLICITUDES = [
  {
    id: 41, estado: "contratada", razon_social_declarada: "Comercial Los Andes Limitada",
    contacto: { nombre: "Contacto de ejemplo", cargo: "Gerente de operaciones", email: "contacto@ejemplo.cl", telefono: "+56 9 0000 0000" },
    consentimientos: { contacto: consentimiento, migracion: consentimiento }, autoriza_migracion: true,
    fecha_creacion: iso(-3), empresa_id: null,
    evaluacion: { id: 9101, completada: true, rubro: "Servicios financieros", puntaje_general: 54.8 },
  },
  {
    id: 42, estado: "nueva", razon_social_declarada: null,
    contacto: { nombre: "Otra persona", cargo: null, email: "otra@ejemplo.cl", telefono: null },
    consentimientos: { contacto: consentimiento, migracion: { aceptado: false, version: null, fecha: null } }, autoriza_migracion: false,
    fecha_creacion: iso(-1), empresa_id: null,
    evaluacion: { id: 9088, completada: false, rubro: null, puntaje_general: null },
  },
];

const ITEM_REVISION = {
  tipo_item: "respuesta", id: 900,
  evaluacion: { id: 9101, origen: "landing", estado_progreso: "completada", cerrada: true, es_prueba: false, empresa: "Empresa de Ejemplo SpA" },
  control: { id: 140, codigo: "GOB-006", pregunta: "¿Existe un responsable formal de la gobernanza de IA?", criticidad: "Alta", dominio_id: 2, dominio: "Gobernanza de IA" },
  declarado: "requiere_revision", estado_final: null, fuente: "llm",
  llm: { clasificacion: "parcialmente_cumplido", confianza: 0.62, fecha: iso(-1), evidencia_id: 71, bajo_umbral: true },
  motivos: ["baja_confianza"], eventos_seguridad: 0, pendiente: true, revision: null, fecha_referencia: iso(-1),
};

export const FIXTURES_ADMIN: TablaFixtures = [
  [/\/admin\/contrataciones$/, pagina(SOLICITUDES)],
  [/\/admin\/empresas$/, pagina([])],
  [/\/rubros$/, [{ id: 3, nombre_rubro: "Servicios financieros" }]],
  [/\/admin\/revision\/bandeja$/, {
    vista: "clasificaciones", estado: "pendiente", motivo: null, ...pagina([ITEM_REVISION]),
    pendientes: { clasificaciones: 1, eventos: 0, por_motivo: { seguridad: 0, divergencia: 0, sin_resolver: 0, baja_confianza: 1, resuelta_por_llm: 0, concordante: 0 } },
    umbral_confianza: 0.7,
  }],
  // 1 revisión: por debajo del mínimo, la métrica no debe mostrarse como porcentaje
  [/\/admin\/revision\/resumen$/, {
    revisadas: 1, confirmadas: 0, corregidas: 1,
    precision_llm: { n_revisadas: 1, accuracy: 0, tasa_error_modelo: 1, f1_macro: 0 },
    eventos: { ataques_confirmados: 0, falsos_positivos: 0, sin_veredicto: 0, precision_deteccion: null },
    umbral_confianza: 0.7,
  }],
  [/\/dominios$/, [{ id: 1, nombre_dominio: "Gestión de Riesgos" }, { id: 2, nombre_dominio: "Gobernanza de IA" }]],
  [/\/arcop\/catalogo$/, { plazo_respuesta_dias: 30, plazo_prorroga_dias: 30, plazo_bloqueo_dias_habiles: 2, plazo_informacion_dias: 10 }],
  [/\/arcop\/solicitudes$/, { items: [], total: 0, page: 1, size: 100, pages: 0 }],
  [/\/admin\/retencion\/ejecuciones$/, pagina([])],
  [/\/admin\/retencion$/, {
    modo: "plazo", fuente: "panel", plazo_titular_dias: 365, activa: true, valor_entorno_dias: 365,
    limites: { min_dias: 30, max_dias: 1825 }, fecha_actualizacion: iso(-10), ejecucion_en_curso_desde: null,
    hora_utc: 3, proxima_ejecucion: new Date(Date.UTC(ahora.getUTCFullYear(), ahora.getUTCMonth(), ahora.getUTCDate() + 1, 3)).toISOString(),
    pendientes: { titulares: 0, fecha_corte: iso(-365), omitidos_por_arcop_abierta: 0 },
    usuarios_sin_vencimiento: 2,
    otras_reglas_dias: { arcop_cerradas: 730, eventos_seguridad: 365, tutor: 180 },
    ultima_ejecucion: null, cambios_recientes: [],
  }],
];
