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

/** HU-29: lo que puede venir de "Mis documentos": PDF, texto anonimizado de evidencias y DOCX (borradores). */
export const TIPOS_DOCUMENTO = [
  "application/pdf",
  "text/plain",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
] as const;

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
