/**
 * HU-15 · Agente IA Tutor del panel de formación (navegador → /bff/cliente/api/tutor).
 *
 * El backend arma el contexto AISLADO (solo las brechas de la evaluación vigente de la
 * empresa del token), llama al agente y guarda los mensajes anonimizados. Aquí solo hay
 * llamadas y presentación, probada en tests/hu15_tutor.test.ts.
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import type {
  ContextoTutorApi,
  ConversacionDetalleApi,
  ConversacionTutorApi,
  CuotaTutorApi,
  ListaConversacionesApi,
  MensajeTutorApi,
  NivelFormativo,
  PasoTutorApi,
  RespuestaTutorApi,
  TipoMensajeTutor,
} from "./types";

export const BASE_TUTOR = "/bff/cliente/api/tutor";
export const MAX_CARACTERES_TUTOR = 2000;
export const NIVELES_TUTOR: NivelFormativo[] = ["Inicial", "Intermedio", "Avanzado"];

/* ------------------------------------------------------------ llamadas */

export const cargarContextoTutor = (rutaId?: number | null) =>
  pedir<ContextoTutorApi>(`${BASE_TUTOR}/contexto${rutaId ? `?ruta_id=${rutaId}` : ""}`);

export const listarConversaciones = () => pedir<ListaConversacionesApi>(`${BASE_TUTOR}/conversaciones`);

export const crearConversacion = (rutaId: number | null, nivel: NivelFormativo | null) =>
  pedir<ConversacionDetalleApi & { contexto: ContextoTutorApi }>(`${BASE_TUTOR}/conversaciones`, {
    method: "POST",
    json: { ruta_id: rutaId ?? null, nivel: nivel ?? null },
  });

export const cargarConversacion = (id: number) => pedir<ConversacionDetalleApi>(`${BASE_TUTOR}/conversaciones/${id}`);

export const cambiarNivelConversacion = (id: number, nivel: NivelFormativo) =>
  pedir<{ conversacion: ConversacionTutorApi }>(`${BASE_TUTOR}/conversaciones/${id}`, { method: "PATCH", json: { nivel } });

export const eliminarConversacion = (id: number) =>
  pedir<void>(`${BASE_TUTOR}/conversaciones/${id}`, { method: "DELETE" });

/** Nunca se reintenta: cada mensaje es una llamada al LLM y gasta cuota. */
export const enviarMensajeTutor = (id: number, texto: string, signal?: AbortSignal) =>
  pedir<RespuestaTutorApi>(`${BASE_TUTOR}/conversaciones/${id}/mensajes`, { method: "POST", json: { texto }, signal });

/* ------------------------------------------------------------ presentación */

export const TIPO_RESPUESTA: Record<TipoMensajeTutor, { etiqueta: string; tono: "ok" | "medio" | "info" | "alto" }> = {
  pregunta: { etiqueta: "Tu pregunta", tono: "info" },
  explicacion: { etiqueta: "Explicación", tono: "info" },
  plan_accion: { etiqueta: "Plan de acción", tono: "ok" },
  orientacion: { etiqueta: "Recomendación", tono: "medio" },
  fuera_de_alcance: { etiqueta: "Fuera de alcance", tono: "info" },
  bloqueado: { etiqueta: "Mensaje bloqueado", tono: "alto" },
};

/** Qué hace el tutor en cada nivel (se muestra junto al selector). */
export const NIVEL_TUTOR_INFO: Record<NivelFormativo, string> = {
  Inicial: "Conceptos simples, el porqué de cada obligación y pocos pasos básicos.",
  Intermedio: "Procedimientos, responsables y la evidencia que debes generar.",
  Avanzado: "Controles, indicadores y cómo auditar el cierre de cada brecha.",
};

export type ValidacionMensaje = { ok: true; texto: string } | { ok: false; motivo: string };

export function validarMensaje(texto: string, max = MAX_CARACTERES_TUTOR): ValidacionMensaje {
  const limpio = texto.trim();
  if (!limpio) return { ok: false, motivo: "Escribe tu pregunta para el tutor." };
  if (limpio.length > max) return { ok: false, motivo: `Tu mensaje supera los ${max} caracteres.` };
  return { ok: true, texto: limpio };
}

/** "Te quedan 57 de 60 mensajes hoy" (o nada si no hay límite). */
export function cuotaTexto(c: CuotaTutorApi | null | undefined): string {
  if (!c || c.limite == null || c.restantes == null) return "";
  if (c.restantes === 0) return `Usaste los ${c.limite} mensajes de hoy. Se reinicia a medianoche.`;
  return `Te ${c.restantes === 1 ? "queda 1 mensaje" : `quedan ${c.restantes} mensajes`} de ${c.limite} hoy.`;
}

/** Preguntas de inicio según el contexto real de la empresa (nunca inventa brechas). */
export function sugerenciasIniciales(ctx: ContextoTutorApi | null): string[] {
  if (!ctx) return [];
  if (!ctx.brechas.length) return ["¿Cómo mantengo el nivel de cumplimiento que ya tengo?"];
  const [primera] = [...ctx.brechas].sort((a, b) => a.prioridad - b.prioridad);
  const s = ["¿Qué brecha debería cerrar primero y por qué?"];
  if (primera) {
    s.push(`Explícame la brecha ${primera.ref} de ${primera.dominio}.`);
    s.push(`Dame un plan de acción para cerrar ${primera.ref}.`);
  }
  if (ctx.foco) s.push(`¿Cómo me ayuda el módulo «${ctx.foco.nombre}» con mis brechas?`);
  else if (ctx.brechas.some((b) => b.estado === "parcialmente_cumplido")) {
    s.push("¿Qué me falta para pasar mis controles parciales a cumplidos?");
  }
  return s.slice(0, 4);
}

/** v1.1: lo que se envía al pulsar "Explícame este paso" (pide detalle de ESE paso, no el plan de nuevo). */
export const preguntaPaso = (p: Pick<PasoTutorApi, "orden" | "accion">) =>
  `Explícame en detalle cómo hago el paso ${p.orden}: «${p.accion}». ¿Por dónde empiezo y qué evidencia debo dejar?`;

/** Párrafos del texto del tutor (sin HTML: React escapa el contenido). */
export const parrafos = (texto: string) =>
  texto
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);

/** La conversación que conviene abrir: la activa más reciente con el mismo foco (o sin foco). */
export function conversacionParaRetomar(items: ConversacionTutorApi[], rutaId: number | null): ConversacionTutorApi | null {
  return items.find((c) => c.estado === "activa" && (c.ruta_id ?? null) === (rutaId ?? null)) ?? null;
}

/** Mensaje provisional del usuario mientras el tutor responde (se reemplaza por el guardado). */
export function mensajeProvisional(texto: string, nivel: NivelFormativo): MensajeTutorApi {
  return {
    id: -Date.now(), rol: "usuario", tipo: "pregunta", contenido: texto, nivel, bloqueado: false,
    fecha: new Date().toISOString(), pasos: [], brechas: [], referencias_normativas: [], sugerencias: [],
  };
}

export function horaCorta(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("es-CL", { timeZone: "America/Santiago", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(d);
}

/** Mensaje para la persona según el código de error del backend o del BFF. */
export function mensajeTutor(e: unknown): string {
  const info = e instanceof ErrorBff ? e.info : null;
  switch (info?.codigo) {
    case "CONTRATO_NO_VIGENTE":
      return "El servicio de tu empresa no está activo. Contacta a Therion Labs para renovarlo.";
    case "NO_AUTORIZADO":
      return "El tutor es parte del servicio contratado: ingresa con la cuenta de tu empresa.";
    case "SESION_EXPIRADA":
      return "Tu sesión terminó. Vuelve a ingresar para seguir.";
    case "CUOTA_TUTOR_AGOTADA":
    case "CUOTA_LLM_GLOBAL_AGOTADA":
    case "TUTOR_RAFAGA":
      return info.mensaje || "Alcanzaste el límite de mensajes. Inténtalo más tarde.";
    case "CONVERSACION_DESACTUALIZADA":
      return "Tu empresa tiene una evaluación más reciente. Abre una conversación nueva para usar tus brechas vigentes.";
    case "CONVERSACION_NO_ENCONTRADA":
      return "Esa conversación ya no existe.";
    case "TUTOR_NO_DISPONIBLE":
    case "LIMITADOR_NO_DISPONIBLE":
      return "El tutor no pudo responder ahora. Tu mensaje no se perdió: inténtalo de nuevo en unos segundos.";
    case "MENSAJE_VACIO":
    case "MENSAJE_DEMASIADO_LARGO":
    case "NIVEL_INVALIDO":
    case "LIMITE_CONVERSACIONES":
    case "RUTA_NO_ENCONTRADA":
      return info.mensaje || "Revisa tu mensaje e inténtalo de nuevo.";
    case "SIN_PLAN":
    case "SIN_RESULTADOS":
      return info.mensaje || "Tu empresa aún no tiene una evaluación con resultados para el tutor.";
    case "SIN_CONEXION":
      return "No pudimos conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.";
    default:
      return info?.mensaje || "No pudimos completar la acción. Inténtalo de nuevo.";
  }
}

/** ¿El error dice que esta sesión no puede usar el tutor? (sin servicio o sin sesión de cliente) */
export const tutorSinServicio = (e: unknown) => e instanceof ErrorBff && (e.status === 401 || e.status === 403);
