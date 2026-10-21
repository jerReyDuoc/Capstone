/**
 * HU-19 · Mensajes para el visitante a partir del código de error.
 * Cada código dice qué pasó y qué puede hacer (sin culpar ni usar jerga técnica).
 */
import type { ErrorEncuesta } from "./contratos";

export type AccionError = "reintentar" | "esperar" | "retomar" | "releer-aviso" | "recargar" | "ninguna";

export interface MensajeError {
  titulo: string;
  detalle: string;
  accion: AccionError;
  /** Segundos que conviene esperar antes de reintentar (429/503). */
  esperaS?: number;
}

const TEXTOS: Record<string, Omit<MensajeError, "esperaS">> = {
  CAPTCHA_INVALIDO: {
    titulo: "No pudimos completar la verificación",
    detalle: "Vuelve a intentarlo. Si usas un bloqueador de anuncios o una VPN, prueba desactivándolo un momento.",
    accion: "reintentar",
  },
  CAPTCHA_PENDIENTE: {
    titulo: "Falta la verificación",
    detalle: "Espera a que termine la verificación de seguridad e inténtalo de nuevo.",
    accion: "reintentar",
  },
  DEMASIADOS_INTENTOS: {
    titulo: "Demasiados intentos seguidos",
    detalle: "Por seguridad hay que esperar unos minutos antes de volver a intentarlo.",
    accion: "esperar",
  },
  LIMITE_EVALUACIONES: {
    titulo: "Se alcanzó el máximo de evaluaciones nuevas por hoy",
    detalle: "Desde tu red ya se iniciaron varias evaluaciones hoy. Si ya empezaste una, puedes retomarla con tu clave.",
    accion: "retomar",
  },
  AVISO_NO_ACEPTADO: {
    titulo: "Falta aceptar el aviso legal",
    detalle: "Para comenzar necesitas leer y aceptar el aviso legal.",
    accion: "releer-aviso",
  },
  AVISO_DESACTUALIZADO: {
    titulo: "El aviso legal se actualizó",
    detalle: "Recarga la página para leer la versión vigente y aceptarla.",
    accion: "recargar",
  },
  RUBRO_INVALIDO: {
    titulo: "El rubro elegido ya no está disponible",
    detalle: "Recarga la página y elige otro rubro.",
    accion: "recargar",
  },
  CREDENCIALES_INVALIDAS: {
    titulo: "Número o clave incorrectos",
    detalle: "Revisa el número de evaluación y la clave de 12 caracteres que guardaste al comenzar.",
    accion: "reintentar",
  },
  SESION_EXPIRADA: {
    titulo: "Tu sesión terminó",
    detalle: "Ingresa de nuevo con tu número de evaluación y tu clave. Tus respuestas están guardadas.",
    accion: "retomar",
  },
  NO_AUTENTICADO: {
    titulo: "Tu sesión terminó",
    detalle: "Ingresa de nuevo con tu número de evaluación y tu clave. Tus respuestas están guardadas.",
    accion: "retomar",
  },
  TOKEN_INVALIDO: {
    titulo: "Tu sesión terminó",
    detalle: "Ingresa de nuevo con tu número de evaluación y tu clave. Tus respuestas están guardadas.",
    accion: "retomar",
  },
  EMAIL_INVALIDO: {
    titulo: "Revisa el correo",
    detalle: "El formato no parece válido (ejemplo: nombre@empresa.cl). También puedes omitir este paso.",
    accion: "reintentar",
  },
  LIMITE_EVIDENCIAS: {
    titulo: "Llegaste al máximo de evidencias",
    detalle: "Puedes seguir respondiendo y justificando tus controles sin adjuntar más archivos.",
    accion: "ninguna",
  },
  LIMITE_EVIDENCIAS_IP: {
    titulo: "Se alcanzó el máximo diario de evidencias desde tu red",
    detalle: "Podrás adjuntar más evidencias mañana. Tus respuestas siguen guardadas.",
    accion: "esperar",
  },
  CUOTA_LLM_AGOTADA: {
    titulo: "Usaste las validaciones con IA de hoy",
    detalle: "Tus respuestas siguen guardadas. Podrás adjuntar más evidencias después del reinicio.",
    accion: "esperar",
  },
  CUOTA_LLM_GLOBAL_AGOTADA: {
    titulo: "La validación con IA está al máximo por hoy",
    detalle: "Tus respuestas siguen guardadas. Podrás adjuntar evidencias después del reinicio.",
    accion: "esperar",
  },
  LIMITADOR_NO_DISPONIBLE: {
    titulo: "Servicio ocupado",
    detalle: "No pudimos procesar la solicitud en este momento. Intenta de nuevo en un minuto.",
    accion: "esperar",
  },
  ORIGEN_NO_PERMITIDO: {
    titulo: "Solicitud no permitida",
    detalle: "Recarga la página e inténtalo de nuevo desde el sitio.",
    accion: "recargar",
  },
  SIN_CONEXION: {
    titulo: "Sin conexión con el servidor",
    detalle: "Revisa tu conexión a internet e inténtalo de nuevo.",
    accion: "reintentar",
  },
};

const GENERICO: Omit<MensajeError, "esperaS"> = {
  titulo: "Algo salió mal",
  detalle: "No pudimos completar la acción. Inténtalo de nuevo en unos segundos.",
  accion: "reintentar",
};

export function mensajeDeError(e: ErrorEncuesta): MensajeError {
  const base = TEXTOS[e.codigo] ?? (e.mensaje ? { ...GENERICO, detalle: e.mensaje } : GENERICO);
  return { ...base, esperaS: e.reintentarEnS };
}

/** "a las 00:00" en la hora de Chile, a partir de un instante ISO en UTC. */
export function horaDeReinicio(iso: string | undefined, zona = "America/Santiago"): string | null {
  if (!iso) return null;
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return null;
  return new Intl.DateTimeFormat("es-CL", { hour: "2-digit", minute: "2-digit", timeZone: zona, hourCycle: "h23" }).format(fecha);
}

/** "2 min", "45 s" — para "vuelve a intentarlo en …". */
export function duracionLegible(segundos: number): string {
  if (segundos < 60) return `${Math.max(1, Math.round(segundos))} s`;
  const min = Math.ceil(segundos / 60);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}
