/**
 * HU-26 · Recorrido de módulos formativos y avance de la empresa (navegador → /bff/cliente/api).
 *
 * Contratos en lib/types.ts (AvanceFormativoApi, ModuloRecorridoApi…). La lógica de negocio
 * (qué se completa, la nota, la constancia) vive en el backend; aquí solo hay presentación,
 * probada en tests/hu26_formacion.test.ts.
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import type {
  AvanceFormativoApi,
  AvanceModuloApi,
  EstadoModulo,
  LeccionApi,
  ModuloAvanceApi,
  ModuloRecorridoApi,
  PreguntaActividadApi,
  ResultadoVerificacionApi,
} from "./types";

export const BASE_FORMACION = "/bff/cliente/api/formacion";

const conEvaluacion = (evaluacionId?: number | null) => (evaluacionId ? `?evaluacion_id=${evaluacionId}` : "");

export const cargarAvance = (evaluacionId?: number | null) =>
  pedir<AvanceFormativoApi>(`${BASE_FORMACION}/avance${conEvaluacion(evaluacionId)}`);

export const cargarModulo = (rutaId: number, evaluacionId?: number | null) =>
  pedir<ModuloRecorridoApi>(`${BASE_FORMACION}/modulos/${rutaId}${conEvaluacion(evaluacionId)}`);

export const marcarLeccionVista = (rutaId: number, orden: number, evaluacionId?: number | null) =>
  pedir<AvanceModuloApi>(`${BASE_FORMACION}/modulos/${rutaId}/lecciones/${orden}/vista`, {
    method: "POST",
    json: { evaluacion_id: evaluacionId ?? null },
  });

export const enviarVerificacion = (rutaId: number, respuestas: Record<number, number>, evaluacionId?: number | null) =>
  pedir<ResultadoVerificacionApi>(`${BASE_FORMACION}/modulos/${rutaId}/verificacion`, {
    method: "POST",
    json: { respuestas, evaluacion_id: evaluacionId ?? null },
  });

/** Descarga la constancia PDF (binaria, con el nombre que propone el servidor). */
export async function descargarConstancia(rutaId: number): Promise<{ blob: Blob; nombre: string }> {
  const res = await fetch(`${BASE_FORMACION}/modulos/${rutaId}/constancia`, { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let info = { codigo: `HTTP_${res.status}`, mensaje: "" };
    try {
      info = ((await res.json()) as { error: typeof info }).error ?? info;
    } catch {
      /* sin cuerpo */
    }
    throw new ErrorBff(res.status, info);
  }
  const m = /filename="?([\w.-]+\.pdf)"?/i.exec(res.headers.get("content-disposition") ?? "");
  return { blob: await res.blob(), nombre: m?.[1] ?? `constancia_modulo-${rutaId}.pdf` };
}

/* ------------------------------------------------------------ presentación */

export const ESTADO_MODULO: Record<EstadoModulo, { etiqueta: string; tono: "ok" | "medio" | "info" }> = {
  no_iniciado: { etiqueta: "Sin empezar", tono: "info" },
  en_curso: { etiqueta: "En curso", tono: "medio" },
  completado: { etiqueta: "Completado", tono: "ok" },
};

/** La acción principal de un módulo en el panel de formación. */
export function accionModulo(m: Pick<ModuloAvanceApi, "estado" | "lecciones_vistas" | "lecciones_total">): string {
  if (m.estado === "completado") return "Ver módulo y constancia";
  if (m.estado === "en_curso") {
    return m.lecciones_vistas >= m.lecciones_total && m.lecciones_total > 0 ? "Hacer la actividad" : "Continuar";
  }
  return "Empezar módulo";
}

export const hrefModulo = (rutaId: number, evaluacionId?: number | null) =>
  `/panel/capacitacion/${rutaId}${evaluacionId ? `?evaluacion=${evaluacionId}` : ""}`;

export const hrefRemediacion = (evaluacionId?: number | null, respuestaId?: number | null) => {
  const q = new URLSearchParams();
  if (evaluacionId) q.set("evaluacion", String(evaluacionId));
  if (respuestaId) q.set("control", String(respuestaId));
  const s = q.toString();
  return `/panel/remediacion${s ? `?${s}` : ""}`;
};

/**
 * Segmentos del medidor de una dimensión: uno por módulo, completados primero, luego en curso
 * y al final los pendientes (la forma del segmento, no solo su color, dice el estado).
 */
export function segmentos(modulos: Pick<ModuloAvanceApi, "estado">[]): EstadoModulo[] {
  const peso: Record<EstadoModulo, number> = { completado: 0, en_curso: 1, no_iniciado: 2 };
  return modulos.map((m) => m.estado).sort((a, b) => peso[a] - peso[b]);
}

export const porcentajeTexto = (n: number) => `${Math.round(n)} %`;

export function resumenAvanceTexto(r: AvanceFormativoApi["resumen"]): string {
  if (r.modulos_total === 0) return "Tu plan no tiene módulos todavía.";
  if (r.completados === r.modulos_total) return `Completaste los ${r.modulos_total} módulos del plan.`;
  const enCurso = r.en_curso ? ` y ${r.en_curso} en curso` : "";
  return `${r.completados} de ${r.modulos_total} módulos completados${enCurso}.`;
}

/** La lección por la que conviene seguir: la primera sin ver (o null si ya vio todas). */
export function siguienteLeccion(lecciones: Pick<LeccionApi, "orden" | "vista">[]): number | null {
  return lecciones.find((l) => !l.vista)?.orden ?? null;
}

export function faltanPorResponder(preguntas: PreguntaActividadApi[], elegidas: Record<number, number>): number[] {
  return preguntas.filter((p) => elegidas[p.id] == null).map((p) => p.id);
}

export const minutosTexto = (min: number | null | undefined) => (min ? `${min} min` : null);

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

/** "2026-10-27T18:30:00" (UTC, del backend) → "27 de octubre de 2026" en hora de Chile. */
export function fechaLarga(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return "—";
  const partes = new Intl.DateTimeFormat("es-CL", {
    timeZone: "America/Santiago", day: "numeric", month: "numeric", year: "numeric",
  }).formatToParts(d);
  const v = (t: string) => Number(partes.find((p) => p.type === t)?.value);
  return `${v("day")} de ${MESES[v("month") - 1]} de ${v("year")}`;
}

/** Mensaje para la persona según el código de error del backend o del BFF. */
export function mensajeFormacion(e: unknown): string {
  const info = e instanceof ErrorBff ? e.info : null;
  switch (info?.codigo) {
    case "CONTRATO_NO_VIGENTE":
      return "El servicio de tu empresa no está activo. Contacta a Therion Labs para renovarlo.";
    case "SESION_EXPIRADA":
      return "Tu sesión terminó. Vuelve a ingresar para seguir.";
    case "LECCIONES_PENDIENTES":
      return "Te faltan lecciones por revisar antes de la actividad.";
    case "LIMITE_INTENTOS":
      return info.mensaje || "Usaste los intentos de hoy. Vuelve a intentarlo mañana.";
    case "MODULO_COMPLETADO":
      return "Ya completaste este módulo. Puedes descargar tu constancia.";
    case "MODULO_NO_ENCONTRADO":
    case "NO_ENCONTRADO":
      return "Este módulo no está en el plan formativo de tu empresa.";
    case "SIN_PLAN":
    case "SIN_RESULTADOS":
      return info.mensaje || "Tu empresa aún no tiene un plan formativo.";
    case "SIN_CONEXION":
      return "No pudimos conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.";
    default:
      return info?.mensaje || "No pudimos completar la acción. Inténtalo de nuevo.";
  }
}

/** ¿El error dice que esta sesión no es de un cliente con servicio? (encuestado o admin en el panel) */
export const esSinServicio = (e: unknown) => e instanceof ErrorBff && (e.status === 401 || e.status === 403 || e.status === 404);
