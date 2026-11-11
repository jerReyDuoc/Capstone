/**
 * HU-25 · Retención de usuarios temporales vencidos (navegador → /bff/admin/api/admin/retencion).
 * Los tipos reflejan app/api/routes/admin_retencion.py. La validación real la hace el backend;
 * aquí solo lo obvio antes de enviar y los textos de la pantalla (lógica pura, probada en tests/).
 */
import { pedir } from "@/lib/encuesta/cliente";

export type ModoRetencion = "entorno" | "plazo" | "desactivada";
export type ResultadoEjecucion = "ok" | "error" | "omitido" | "rechazado";
export type OrigenEjecucion = "cron" | "manual" | "cli";

export interface Pendientes {
  titulares: number;
  omitidos_por_arcop_abierta: number;
  fecha_corte: string;
}

export interface DetalleEjecucion {
  origen: OrigenEjecucion;
  simulacion: boolean;
  inicio: string;
  duracion_ms: number;
  plazos_dias: { titulares: number | null; arcop: number | null; eventos: number | null; tutor: number | null };
  fuente_plazo_titulares: string;
  fecha_corte_titulares: string | null;
  reglas_desactivadas: string[];
  conteos: {
    titulares: number;
    titulares_omitidos_por_arcop_abierta: number;
    titulares_fallidos: number;
    solicitudes_arcop: number;
    eventos_seguridad: number;
    conversaciones_tutor: number;
    archivos_borrados: number;
  };
  omitida_por_ejecucion_en_curso: boolean;
  error: string | null;
}

export interface RegistroLog<D = Record<string, unknown>> {
  id: number;
  fecha: string;
  actor_rol: string;
  actor_id: number | null;
  resultado: ResultadoEjecucion;
  detalle: D | null;
}

export interface CambioPlazo {
  regla: string;
  antes: { modo: ModoRetencion; plazo_titular_dias: number | null };
  despues: { modo: ModoRetencion; plazo_titular_dias: number | null };
}

export interface EstadoRetencion {
  modo: ModoRetencion;
  fuente: "entorno" | "panel";
  plazo_titular_dias: number | null;
  activa: boolean;
  valor_entorno_dias: number | null;
  limites: { min_dias: number; max_dias: number };
  fecha_actualizacion: string | null;
  ejecucion_en_curso_desde: string | null;
  hora_utc: number;
  proxima_ejecucion: string;
  pendientes: Pendientes | null;
  usuarios_sin_vencimiento: number;
  otras_reglas_dias: { arcop_cerradas: number | null; eventos_seguridad: number | null; tutor: number | null };
  ultima_ejecucion: RegistroLog<DetalleEjecucion> | null;
  cambios_recientes: RegistroLog<CambioPlazo>[];
}

export interface ResultadoSimulacion {
  simulacion: boolean;
  titulares: number;
  titulares_omitidos_por_arcop_abierta: number;
  solicitudes_arcop: number;
  eventos_seguridad: number;
  conversaciones_tutor: number;
  reglas_desactivadas: string[];
  plazo_titular_dias: number | null;
  ejecucion_id: number | null;
}

const BASE = "/bff/admin/api/admin/retencion";

export const apiRetencion = {
  estado: () => pedir<EstadoRetencion>(BASE),
  cambiar: (modo: ModoRetencion, plazo_titular_dias: number | null) =>
    pedir<EstadoRetencion>(BASE, { method: "PATCH", json: { modo, plazo_titular_dias } }),
  vistaPrevia: (dias: number) =>
    pedir<{ plazo_titular_dias: number; pendientes: Pendientes }>(`${BASE}/vista-previa?dias=${dias}`),
  simular: () => pedir<ResultadoSimulacion>(`${BASE}/simulacion`, { method: "POST", json: {} }),
  ejecutar: () =>
    pedir<{ encolada: boolean; ya_en_cola: boolean; mensaje: string }>(`${BASE}/ejecuciones`, {
      method: "POST",
      json: { confirmar: true },
    }),
  ejecuciones: (page = 1, size = 20) =>
    pedir<{ items: RegistroLog<DetalleEjecucion>[]; total: number; page: number; size: number }>(
      `${BASE}/ejecuciones?page=${page}&size=${size}`,
    ),
};

/** Error para mostrar junto al campo del plazo, o null si se puede enviar. */
export function errorPlazo(texto: string, limites: { min_dias: number; max_dias: number }): string | null {
  const t = texto.trim();
  if (!/^\d{1,5}$/.test(t)) return "Escribe un número entero de días.";
  const n = Number(t);
  if (n < limites.min_dias || n > limites.max_dias) {
    return `El plazo debe estar entre ${limites.min_dias} y ${limites.max_dias} días.`;
  }
  return null;
}

/** "365 días (1 año)": ayuda a leer plazos largos. */
export function plazoLegible(dias: number | null | undefined): string {
  if (dias == null) return "sin plazo";
  const base = `${dias} ${dias === 1 ? "día" : "días"}`;
  if (dias >= 365 && dias % 365 === 0) {
    const anios = dias / 365;
    return `${base} (${anios} ${anios === 1 ? "año" : "años"})`;
  }
  if (dias >= 30 && dias % 30 === 0 && dias < 365) {
    const meses = dias / 30;
    return `${base} (${meses} ${meses === 1 ? "mes" : "meses"})`;
  }
  return base;
}

/** Plazo que rige hoy, en una frase. */
export function describirPlazo(e: Pick<EstadoRetencion, "modo" | "plazo_titular_dias" | "valor_entorno_dias">): string {
  if (e.modo === "desactivada") return "Desactivada: los datos de los usuarios temporales vencidos no se anonimizan.";
  if (e.plazo_titular_dias == null) {
    return "Sin plazo: falta fijarlo (RETENCION_DATOS_TITULAR_DIAS está vacía). Los datos no se anonimizan.";
  }
  const origen = e.modo === "entorno" ? " (valor por defecto del servidor)" : " (fijado en este panel)";
  return `${plazoLegible(e.plazo_titular_dias)} después de que vence el acceso${origen}.`;
}

/**
 * Pide confirmación al guardar si el cambio ADELANTA la anonimización (bajar el plazo o activar
 * la regla) y hay titulares que se anonimizarían en la próxima ejecución, o no se sabe cuántos
 * (pendientesNuevo = null: la vista previa no está disponible). Alargar o desactivar no pide.
 */
export function requiereConfirmacion(actual: number | null, nuevo: number | null, pendientesNuevo: number | null): boolean {
  if (nuevo == null) return false;
  const adelanta = actual == null || nuevo < actual;
  if (!adelanta) return false;
  return pendientesNuevo === null || pendientesNuevo > 0;
}

/** Texto de la confirmación antes de guardar un plazo que adelanta la anonimización. */
export function textoConfirmacion(pendientesNuevo: number | null): string {
  if (pendientesNuevo === null) {
    return "Este cambio puede anonimizar usuarios temporales en la próxima ejecución. No se puede deshacer.";
  }
  const quien = pendientesNuevo === 1 ? "usuario temporal" : "usuarios temporales";
  return `En la próxima ejecución se anonimizarán ${pendientesNuevo} ${quien}. No se puede deshacer.`;
}

export const ETIQUETA_ORIGEN: Record<OrigenEjecucion, string> = {
  cron: "Programada",
  manual: "Manual (panel)",
  cli: "Manual (consola)",
};

export function etiquetaResultado(r: RegistroLog<DetalleEjecucion>): { texto: string; tono: "ok" | "alto" | "medio" | "info" } {
  if (r.resultado === "omitido") return { texto: "Omitida (otra en curso)", tono: "medio" };
  if (r.resultado === "error") {
    const fallidos = r.detalle?.conteos.titulares_fallidos ?? 0;
    return { texto: r.detalle?.error ? "Falló" : `Con ${fallidos} ${fallidos === 1 ? "fallo" : "fallos"}`, tono: "alto" };
  }
  return r.detalle?.simulacion ? { texto: "Simulación", tono: "info" } : { texto: "Completada", tono: "ok" };
}

/** Resumen de una ejecución en una línea (sin datos personales: solo conteos). */
export function resumenEjecucion(d: DetalleEjecucion | null): string {
  if (!d) return "—";
  if (d.omitida_por_ejecucion_en_curso) return "No se ejecutó: había otra ejecución en curso.";
  const c = d.conteos;
  const uno = c.titulares === 1;
  const verbo = d.simulacion ? (uno ? "se anonimizaría" : "se anonimizarían") : uno ? "anonimizado" : "anonimizados";
  const partes = [`${c.titulares} ${uno ? "usuario temporal" : "usuarios temporales"} ${verbo}`];
  if (c.titulares_omitidos_por_arcop_abierta) partes.push(`${c.titulares_omitidos_por_arcop_abierta} en espera por ARCOP abierta`);
  if (c.titulares_fallidos) partes.push(`${c.titulares_fallidos} con error`);
  const otras = c.solicitudes_arcop + c.eventos_seguridad + c.conversaciones_tutor;
  if (otras) partes.push(`${otras} ${otras === 1 ? "registro" : "registros"} de otras reglas`);
  if (d.reglas_desactivadas.includes("titulares")) partes.push("regla de titulares sin plazo");
  return partes.join(" · ");
}

/** Lo que borra la anonimización (la misma de una supresión ARCOP aprobada) y lo que conserva. */
export const SE_ANONIMIZA = [
  "Correo y validación de la invitación del usuario temporal",
  "Clave de acceso de la encuesta pública",
  "Justificaciones escritas en las respuestas",
  "Evidencias: nombre, archivo, huella y resultado de la IA",
  "Huellas del motor NER y extractos de eventos de seguridad",
  "Textos del titular en sus solicitudes ARCOP y contactos comerciales no migrados",
] as const;

export const SE_CONSERVA = [
  "Estado y clasificación de cada control (puntajes)",
  "Resumen por dimensión y nivel de madurez",
  "Rubro y fechas, para la comparativa sectorial (benchmark)",
  "Evaluaciones ya migradas a una empresa cliente (contrato, HU-27/HU-30)",
] as const;
