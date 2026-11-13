/**
 * HU-28 · Lista blanca del proxy del usuario definitivo /bff/cliente/api/* (lógica pura,
 * probada en tests/).
 *
 * El cliente entra al espacio de su empresa y, desde ahí, ve los resultados de las
 * evaluaciones migradas con el mismo panel que el encuestado (/panel en modo "cliente").
 * HU-15 agrega el chat con el Agente IA Tutor (sus conversaciones admiten PATCH del nivel
 * y DELETE).
 *
 * HU-29: el cliente inicia reevaluaciones desde la cuenta y las responde con su sesión, así
 * que ahora pasan también las rutas del cuestionario (filtro, respuestas, evidencias y
 * /completar). El historial migrado sigue sin reescribirse: esas evaluaciones están
 * completadas y el backend rechaza cualquier cambio (409). Siguen fuera PUT de respuestas,
 * /cerrar (recalcular un resumen) y todo DELETE sobre evaluaciones. Además: "Mis
 * evaluaciones" y "Mis documentos" (descarga y eliminación).
 *
 * HU-16: borradores de cumplimiento (generar, revisar, editar con PATCH, descargar en
 * Markdown o PDF, consolidar y descartar). Generar espera al Agente IA: hasta 90 s.
 *
 * Informe RoPA del registro de actividades: vista previa, datos de contacto (PATCH), emisión y descarga.
 *
 * HU-32: derechos ARCOP del usuario definitivo (con o sin contrato vigente, HU-30): crear,
 * consultar, cancelar, aportar información y descargar sus datos (JSON o CSV) cuando una
 * solicitud de acceso o portabilidad está resuelta.
 *
 * La autorización real la hace FastAPI (app/core/alcance.py): el rol cliente solo ve las
 * evaluaciones migradas a SU empresa (404 en cualquier otra).
 */

export type MetodoCliente = "GET" | "POST" | "PATCH" | "DELETE";

interface Regla {
  metodo: MetodoCliente;
  patron: RegExp;
  binario?: boolean;
  /** HU-29: tipos de contenido admitidos en una respuesta binaria (por defecto solo PDF). */
  tipos?: readonly string[];
  conIp?: boolean;
  timeoutMs?: number;
  /** Subida de archivos (multipart): HU-17. */
  archivo?: boolean;
}

/** Planilla Excel (informe del registro de actividades). */
export const TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/**
 * HU-29: lo que puede venir de "Mis documentos": PDF, texto anonimizado de evidencias, DOCX (borradores)
 * y XLSX (informe del registro de actividades).
 */
export const TIPOS_DOCUMENTO = [
  "application/pdf",
  "text/plain",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  TIPO_XLSX,
] as const;

/** Informe del registro de actividades: PDF o planilla Excel. */
export const TIPOS_INFORME_RAT = ["application/pdf", TIPO_XLSX] as const;

/** HU-16: la descarga previa de un borrador es Markdown o PDF. */
export const TIPOS_BORRADOR = ["application/pdf", "text/markdown"] as const;

/** HU-32: la exportación de datos del titular ARCOP es JSON (portabilidad) o CSV (planilla). */
export const TIPOS_EXPORTACION_ARCOP_CLIENTE = ["application/json", "text/csv"] as const;

const REGLAS: Regla[] = [
  // Espacio de la empresa (HU-28; HU-29 lo amplía)
  { metodo: "GET", patron: /^cliente\/empresa$/ },
  // HU-30: situación del contrato (responde también sin contrato vigente)
  { metodo: "GET", patron: /^cliente\/contrato$/ },
  // HU-29: "Mis evaluaciones" (historial y reevaluación) y "Mis documentos"
  { metodo: "GET", patron: /^cliente\/evaluaciones$/ },
  { metodo: "POST", patron: /^cliente\/evaluaciones$/ },
  { metodo: "GET", patron: /^cliente\/documentos$/ },
  { metodo: "POST", patron: /^cliente\/documentos\/informes$/, timeoutMs: 30_000 },
  { metodo: "GET", patron: /^cliente\/documentos\/\d{1,9}\/descarga$/, binario: true, tipos: TIPOS_DOCUMENTO, timeoutMs: 30_000 },
  { metodo: "GET", patron: /^cliente\/documentos\/evidencias\/\d{1,9}\/descarga$/, binario: true, tipos: TIPOS_DOCUMENTO, timeoutMs: 30_000 },
  { metodo: "DELETE", patron: /^cliente\/documentos\/\d{1,9}$/ },
  { metodo: "DELETE", patron: /^cliente\/documentos\/(evidencias|constancias)\/\d{1,9}$/ },
  // Evaluaciones de la empresa: listado y resultados (lectura)
  { metodo: "GET", patron: /^evaluaciones$/ },
  { metodo: "GET", patron: /^evaluaciones\/\d{1,9}$/ },
  { metodo: "GET", patron: /^evaluaciones\/\d{1,9}\/(respuestas|resumen|comparativa|progreso|plan-formativo|filtro|controles-aplicables)$/ },
  // HU-29: responder la reevaluación (las migradas están completadas: el backend responde 409)
  { metodo: "POST", patron: /^evaluaciones\/\d{1,9}\/(filtro|completar)$/ },
  { metodo: "POST", patron: /^respuestas$/ },
  { metodo: "GET", patron: /^respuestas\/\d{1,9}$/ },
  { metodo: "POST", patron: /^respuestas\/\d{1,9}\/evidencias$/, archivo: true, conIp: true, timeoutMs: 60_000 },
  { metodo: "GET", patron: /^evidencias\/\d{1,9}$/ },
  { metodo: "GET", patron: /^evaluaciones\/\d{1,9}\/informe\/pdf$/, binario: true, timeoutMs: 30_000 },
  // HU-21: ficha del informe (portada del PDF en JSON)
  { metodo: "GET", patron: /^evaluaciones\/\d{1,9}\/informe\/ficha$/, timeoutMs: 30_000 },
  { metodo: "POST", patron: /^evaluaciones\/\d{1,9}\/informe\/enviar$/, conIp: true, timeoutMs: 45_000 },
  // Catálogos (públicos, sin datos personales)
  { metodo: "GET", patron: /^(brechas|dominios|rubros|rutas-formativas|controles)$/ },
  // HU-26: recorrido de los módulos del plan formativo y avance de la empresa
  { metodo: "GET", patron: /^formacion\/avance$/ },
  { metodo: "GET", patron: /^formacion\/modulos\/\d{1,9}$/ },
  { metodo: "POST", patron: /^formacion\/modulos\/\d{1,9}\/lecciones\/\d{1,4}\/vista$/ },
  { metodo: "POST", patron: /^formacion\/modulos\/\d{1,9}\/verificacion$/ },
  { metodo: "GET", patron: /^formacion\/modulos\/\d{1,9}\/constancia$/, binario: true, timeoutMs: 30_000 },
  // HU-17: remediación (subir evidencia nueva de un control con brecha)
  { metodo: "GET", patron: /^remediacion\/evaluaciones\/\d{1,9}$/ },
  { metodo: "POST", patron: /^remediacion\/respuestas\/\d{1,9}\/evidencias$/, archivo: true, conIp: true, timeoutMs: 60_000 },
  { metodo: "GET", patron: /^remediacion\/evidencias\/\d{1,9}$/ },
  // HU-15: Agente IA Tutor del panel de formación (cada mensaje espera al LLM: hasta 60 s)
  { metodo: "GET", patron: /^tutor\/contexto$/ },
  { metodo: "GET", patron: /^tutor\/conversaciones$/ },
  { metodo: "POST", patron: /^tutor\/conversaciones$/ },
  { metodo: "GET", patron: /^tutor\/conversaciones\/\d{1,9}$/ },
  { metodo: "PATCH", patron: /^tutor\/conversaciones\/\d{1,9}$/ },
  { metodo: "DELETE", patron: /^tutor\/conversaciones\/\d{1,9}$/ },
  { metodo: "POST", patron: /^tutor\/conversaciones\/\d{1,9}\/mensajes$/, timeoutMs: 60_000 },
  // HU-16: borradores de cumplimiento (generar espera al Agente IA)
  { metodo: "GET", patron: /^borradores\/plantillas$/ },
  { metodo: "GET", patron: /^borradores$/ },
  { metodo: "POST", patron: /^borradores$/, timeoutMs: 90_000 },
  { metodo: "GET", patron: /^borradores\/\d{1,9}$/ },
  { metodo: "PATCH", patron: /^borradores\/\d{1,9}$/ },
  { metodo: "DELETE", patron: /^borradores\/\d{1,9}$/ },
  { metodo: "GET", patron: /^borradores\/\d{1,9}\/descarga$/, binario: true, tipos: TIPOS_BORRADOR, timeoutMs: 30_000 },
  { metodo: "POST", patron: /^borradores\/\d{1,9}\/consolidacion$/, timeoutMs: 30_000 },
  // HU-32: derechos ARCOP del usuario definitivo (disponibles siempre, también sin contrato)
  { metodo: "GET", patron: /^arcop\/catalogo$/ },
  { metodo: "GET", patron: /^arcop\/solicitudes$/ },
  { metodo: "GET", patron: /^arcop\/solicitudes\/\d{1,9}$/ },
  { metodo: "POST", patron: /^arcop\/solicitudes$/ },
  { metodo: "POST", patron: /^arcop\/solicitudes\/\d{1,9}\/(cancelacion|informacion)$/ },
  { metodo: "GET", patron: /^arcop\/solicitudes\/\d{1,9}\/exportacion$/, binario: true, tipos: TIPOS_EXPORTACION_ARCOP_CLIENTE, timeoutMs: 30_000 },
  // Mapa de datos personales (servicio contratado): elementos, flujos, plantillas, sugerencias,
  // versiones e informe PDF (descarga y envío por correo).
  { metodo: "GET", patron: /^mapa-datos$/ },
  { metodo: "GET", patron: /^mapa-datos\/(catalogo|plantillas|sugerencias|versiones)$/ },
  { metodo: "GET", patron: /^mapa-datos\/versiones\/\d{1,9}$/ },
  { metodo: "POST", patron: /^mapa-datos\/(elementos|flujos|revision)$/ },
  { metodo: "PATCH", patron: /^mapa-datos\/(elementos|flujos)\/\d{1,9}$/ },
  { metodo: "DELETE", patron: /^mapa-datos\/(elementos|flujos)\/\d{1,9}$/ },
  { metodo: "POST", patron: /^mapa-datos\/plantillas\/aplicar$/ },
  { metodo: "POST", patron: /^mapa-datos\/sugerencias\/restablecer$/ },
  { metodo: "POST", patron: /^mapa-datos\/sugerencias\/[a-z_]{1,40}\/(aceptar|descartar)$/ },
  { metodo: "POST", patron: /^mapa-datos\/versiones\/\d{1,9}\/restaurar$/ },
  { metodo: "GET", patron: /^mapa-datos\/informe\/pdf$/, binario: true, timeoutMs: 45_000 },
  { metodo: "POST", patron: /^mapa-datos\/informe\/enviar$/, timeoutMs: 45_000 },
  // Registro de actividades de tratamiento (servicio contratado): actividades, estados y versiones.
  { metodo: "GET", patron: /^registro-actividades$/ },
  { metodo: "GET", patron: /^registro-actividades\/catalogo$/ },
  { metodo: "POST", patron: /^registro-actividades\/actividades$/ },
  { metodo: "GET", patron: /^registro-actividades\/actividades\/\d{1,9}$/ },
  { metodo: "PATCH", patron: /^registro-actividades\/actividades\/\d{1,9}$/ },
  { metodo: "POST", patron: /^registro-actividades\/actividades\/\d{1,9}\/estado$/ },
  { metodo: "GET", patron: /^registro-actividades\/actividades\/\d{1,9}\/versiones$/ },
  { metodo: "GET", patron: /^registro-actividades\/actividades\/\d{1,9}\/versiones\/\d{1,9}$/ },
  // Informe del registro (PDF y Excel): vista previa e historial, emisión (arma los dos archivos),
  // descarga, envío por correo y verificación de un código.
  { metodo: "GET", patron: /^registro-actividades\/informes$/, timeoutMs: 30_000 },
  { metodo: "POST", patron: /^registro-actividades\/informes$/, timeoutMs: 90_000 },
  { metodo: "GET", patron: /^registro-actividades\/informes\/verificacion$/ },
  { metodo: "GET", patron: /^registro-actividades\/informes\/\d{1,9}\/descarga$/, binario: true, tipos: TIPOS_INFORME_RAT, timeoutMs: 30_000 },
  { metodo: "POST", patron: /^registro-actividades\/informes\/\d{1,9}\/enviar$/, timeoutMs: 60_000 },
  // Informe RoPA: vista previa, datos que el registro no tiene (PATCH), emisión (PDF y Excel) y descarga.
  { metodo: "GET", patron: /^registro-actividades\/ropa$/, timeoutMs: 30_000 },
  { metodo: "PATCH", patron: /^registro-actividades\/ropa\/datos$/ },
  { metodo: "POST", patron: /^registro-actividades\/ropa$/, timeoutMs: 90_000 },
  { metodo: "GET", patron: /^registro-actividades\/ropa\/\d{1,9}\/descarga$/, binario: true, tipos: TIPOS_INFORME_RAT, timeoutMs: 30_000 },
  // Asistente de registro: entrevista guiada, documentos y propuestas que el usuario acepta o descarta.
  // Responder y analizar un documento llaman al servicio de IA: más tiempo.
  { metodo: "GET", patron: /^asistente$/ },
  { metodo: "POST", patron: /^asistente\/sesiones$/ },
  { metodo: "POST", patron: /^asistente\/sesiones\/\d{1,9}\/(area|cerrar)$/ },
  { metodo: "POST", patron: /^asistente\/sesiones\/\d{1,9}\/respuestas$/, timeoutMs: 90_000 },
  { metodo: "POST", patron: /^asistente\/documentos$/, archivo: true, timeoutMs: 120_000 },
  { metodo: "POST", patron: /^asistente\/propuestas\/\d{1,9}\/(aceptar|descartar)$/, timeoutMs: 30_000 },
];

const SEGMENTO = /^[A-Za-z0-9_-]{1,64}$/;

export type AutorizacionCliente =
  | { ok: true; ruta: string; binario: boolean; conIp: boolean; archivo: boolean; timeoutMs?: number; tipos?: readonly string[] }
  | { ok: false };

export function autorizarRutaCliente(metodo: string, segmentos: string[]): AutorizacionCliente {
  if (!segmentos.length || segmentos.length > 6 || !segmentos.every((s) => SEGMENTO.test(s))) return { ok: false };
  const ruta = segmentos.join("/");
  const regla = REGLAS.find((r) => r.metodo === metodo && r.patron.test(ruta));
  if (!regla) return { ok: false };
  return {
    // FastAPI define POST /api/respuestas/ con barra final (igual que el proxy del encuestado)
    ok: true, ruta: ruta === "respuestas" ? "respuestas/" : ruta, binario: Boolean(regla.binario),
    conIp: Boolean(regla.conIp), archivo: Boolean(regla.archivo), timeoutMs: regla.timeoutMs,
    ...(regla.tipos ? { tipos: regla.tipos } : {}),
  };
}

/** HU-29: las respuestas del cuestionario llevan la justificación (hasta 64 KB de JSON). */
export const MAX_BYTES_JSON_CLIENTE = 64 * 1024;
/** HU-17: evidencias de remediación (el backend corta en EVIDENCIA_MAX_MB, 10 MB por defecto). */
export const MAX_BYTES_ARCHIVO_CLIENTE = 12 * 1024 * 1024;
