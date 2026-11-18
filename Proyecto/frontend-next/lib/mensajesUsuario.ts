/**
 * Auditoría UX 16-11 · Fase 6: un solo lugar para traducir errores técnicos a lenguaje de usuario.
 *
 * El backend a veces devuelve textos pensados para el equipo técnico ("Bloqueo preventivo: posible
 * prompt injection… no fue enviada al LLM", "Error 502 al consultar /api/…", nombres de excepción).
 * Nada de eso debe llegar a la pantalla del cliente: se reemplaza por qué pasó y qué puede hacer.
 *
 * - `mensajeEvidencia(texto)`: motivo de una evidencia rechazada o con error.
 * - `textoSeguro(texto, respaldo)`: cualquier texto del servidor; si trae jerga técnica, usa el respaldo.
 * - `mensajePorCodigo(codigo)`: códigos de error HTTP/BFF frecuentes → mensaje claro.
 */

export const MENSAJE_EVIDENCIA_BLOQUEADA =
  "No pudimos analizar este archivo. Revisa que no contenga instrucciones o texto inusual y súbelo de nuevo.";

export const MENSAJE_EVIDENCIA_ERROR = "No pudimos analizar este archivo. Vuelve a intentarlo en unos minutos.";

export const MENSAJE_GENERICO = "Algo no salió como esperábamos. Vuelve a intentarlo en unos minutos.";

export const MENSAJE_SIN_CONEXION = "No pudimos conectarnos. Revisa tu conexión a internet y vuelve a intentarlo.";

/** Términos que delatan un mensaje técnico (no deben verse en la interfaz del cliente). */
const JERGA = [
  /\bLLM\b/i,
  /\bprompt\b/i,
  /\binjection\b/i,
  /\btokens?\b/i,
  /\bHTTP\b/,
  /\b[45]\d\d\b.*\b(error|status)\b|\berror\s+[45]\d\d\b/i,
  /traceback|exception|stack ?trace|\bnull\b|undefined/i,
  /\/api\//,
  /\bid[_ ]?\d+\b|\(id \d+\)/i,
  /\b[A-Z][A-Z_]{4,}\b/, // CODIGO_INTERNO
];

export const tieneJerga = (texto: string) => JERGA.some((r) => r.test(texto));

const esBloqueoSeguridad = (texto: string) =>
  /^bloqueo preventivo/i.test(texto.trim()) || /prompt injection|instrucciones (maliciosas|a la ia)/i.test(texto);

/** Texto del servidor apto para mostrar: el original si es claro; si no, el respaldo. */
export function textoSeguro(texto: string | null | undefined, respaldo = MENSAJE_GENERICO): string {
  const t = (texto ?? "").trim();
  if (!t) return respaldo;
  if (esBloqueoSeguridad(t)) return MENSAJE_EVIDENCIA_BLOQUEADA;
  return tieneJerga(t) ? respaldo : t;
}

/** Motivo de una evidencia rechazada o con error, en lenguaje de usuario. */
export function mensajeEvidencia(texto: string | null | undefined, respaldo = MENSAJE_EVIDENCIA_ERROR): string {
  return textoSeguro(texto, respaldo);
}

const POR_CODIGO: Record<string, string> = {
  SIN_CONEXION: MENSAJE_SIN_CONEXION,
  HTTP_401: "Tu sesión terminó. Vuelve a ingresar para continuar.",
  HTTP_403: "No tienes permiso para ver esto con tu cuenta.",
  HTTP_404: "No encontramos lo que buscabas. Puede que se haya eliminado.",
  HTTP_409: "Alguien cambió estos datos mientras los editabas. Recarga para ver la versión actual.",
  HTTP_413: "El archivo es demasiado grande.",
  HTTP_429: "Hiciste muchos intentos seguidos. Espera un momento y vuelve a intentarlo.",
  HTTP_500: MENSAJE_GENERICO,
  HTTP_502: "El servicio no responde en este momento. Vuelve a intentarlo en unos minutos.",
  HTTP_503: "El servicio no responde en este momento. Vuelve a intentarlo en unos minutos.",
  HTTP_504: "El servicio tardó demasiado en responder. Vuelve a intentarlo en unos minutos.",
};

/** Mensaje claro para un código de error (o el genérico). */
export function mensajePorCodigo(codigo: string | null | undefined): string {
  return (codigo && POR_CODIGO[codigo]) || MENSAJE_GENERICO;
}

/** Mensaje claro para un estado HTTP. */
export const mensajePorEstado = (status: number) => (status === 0 ? MENSAJE_SIN_CONEXION : mensajePorCodigo(`HTTP_${status}`));
