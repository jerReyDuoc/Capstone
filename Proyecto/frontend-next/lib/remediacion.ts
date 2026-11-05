/**
 * HU-17 · Remediación: subir evidencia nueva para re-evaluar un control (navegador → /bff/cliente/api).
 *
 * El backend valida el tipo por contenido, extrae el texto, lo anonimiza y decide con el LLM;
 * aquí solo se valida lo obvio antes de subir (para no gastar un intento) y se presentan los
 * resultados. Probado en tests/hu17_remediacion.test.ts.
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import type {
  ControlRemediacionApi, DominioVista, EstadoClasificacion, EvidenciaRemediacionApi, MejoraRemediacionApi, RemediacionApi,
} from "./types";

export const BASE_REMEDIACION = "/bff/cliente/api/remediacion";

export const cargarRemediacion = (evaluacionId: number) =>
  pedir<RemediacionApi>(`${BASE_REMEDIACION}/evaluaciones/${evaluacionId}`);

export const consultarEvidencia = (evidenciaId: number) =>
  pedir<EvidenciaRemediacionApi>(`${BASE_REMEDIACION}/evidencias/${evidenciaId}`, {}, { reintentos: 1 });

export async function subirEvidencia(
  respuestaId: number,
  archivo: File,
  estadoDeclarado: "cumplido" | "parcialmente_cumplido",
  justificacion: string,
): Promise<EvidenciaRemediacionApi> {
  const form = new FormData();
  form.append("file", archivo, archivo.name);
  form.append("estado_declarado", estadoDeclarado);
  if (justificacion.trim()) form.append("justificacion", justificacion.trim());
  return pedir<EvidenciaRemediacionApi>(`${BASE_REMEDIACION}/respuestas/${respuestaId}/evidencias`, {
    method: "POST",
    body: form,
  });
}

/* ------------------------------------------------------------ validación previa */

export const EXTENSIONES_ADMITIDAS = [".pdf", ".docx", ".txt"] as const;
export const ACCEPT = ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

/** Error para mostrar junto al campo, o null si el archivo se puede subir. */
export function validarArchivo(archivo: Pick<File, "name" | "size"> | null, maxMb: number): string | null {
  if (!archivo) return "Elige el archivo de la evidencia.";
  const nombre = archivo.name.toLowerCase();
  if (!EXTENSIONES_ADMITIDAS.some((e) => nombre.endsWith(e))) {
    return "Sube un PDF, un Word (.docx) o un texto (.txt).";
  }
  if (archivo.size === 0) return "El archivo está vacío.";
  if (archivo.size > maxMb * 1024 * 1024) return `El archivo pesa más de ${maxMb} MB. Comprímelo o divídelo.`;
  return null;
}

/** Los estados a los que se puede declarar que llegó el control (siempre mejores que el actual). */
export function estadosDeclarables(actual: ControlRemediacionApi["estado"]): ("cumplido" | "parcialmente_cumplido")[] {
  return actual === "parcialmente_cumplido" ? ["cumplido"] : ["cumplido", "parcialmente_cumplido"];
}

export const ETIQUETA_ESTADO: Record<EstadoClasificacion, string> = {
  cumplido: "Cumplido",
  parcialmente_cumplido: "Parcialmente cumplido",
  no_cumplido: "No cumplido",
  no_aplica: "No aplica",
  requiere_revision: "En revisión",
};

export const TONO_ESTADO: Record<EstadoClasificacion, "ok" | "medio" | "alto" | "info"> = {
  cumplido: "ok",
  parcialmente_cumplido: "medio",
  no_cumplido: "alto",
  no_aplica: "info",
  requiere_revision: "info",
};

export type FaseEvidencia = "analizando" | "mejoro" | "sin-cambio" | "error";

export function faseEvidencia(e: Pick<EvidenciaRemediacionApi, "en_proceso" | "mejoro" | "estado_validacion">): FaseEvidencia {
  if (e.en_proceso) return "analizando";
  if (e.mejoro) return "mejoro";
  if (e.estado_validacion === "error") return "error";
  return "sin-cambio";
}

/** Texto de resultado de una evidencia ya analizada. */
export function resultadoTexto(e: EvidenciaRemediacionApi): string {
  switch (faseEvidencia(e)) {
    case "analizando":
      return "Estamos analizando la evidencia. Esto suele tardar menos de un minuto.";
    case "mejoro": {
      const delta = deltaTexto(e.puntaje_previo, e.puntaje_resultante);
      return `El control pasó de ${ETIQUETA_ESTADO[e.estado_previo ?? "no_cumplido"].toLowerCase()} a ${ETIQUETA_ESTADO[e.estado_resultante ?? "cumplido"].toLowerCase()}. ${
        delta && delta !== "sin cambios" ? `Tu puntaje general subió ${delta}.` : "Actualizamos tu puntaje."
      }`;
    }
    case "error":
      return e.errores_validacion[0] ?? "No pudimos analizar el archivo. Vuelve a intentarlo.";
    default:
      return e.errores_validacion.at(-1) ?? "La evidencia no cambió el estado del control.";
  }
}

/**
 * Espera entre consultas mientras se analiza: rápido al principio y luego más espaciado.
 * null = dejar de consultar (al pasar unos 3 minutos; el resultado se verá al volver).
 */
export function esperaConsulta(intento: number): number | null {
  if (intento >= 40) return null;
  return Math.min(1500 * 1.25 ** intento, 8000);
}

/** "+3,6 pts" / "−1 pt" / "sin cambios" (con coma decimal, como el resto del panel). */
export function deltaTexto(antes: number | null | undefined, despues: number | null | undefined): string {
  if (antes == null || despues == null) return "";
  const d = Math.round((despues - antes) * 10) / 10;
  if (d === 0) return "sin cambios";
  const n = Math.abs(d).toString().replace(".", ",");
  return `${d > 0 ? "+" : "−"}${n} ${Math.abs(d) === 1 ? "pt" : "pts"}`;
}

export function mensajeRemediacion(e: unknown): string {
  const info = e instanceof ErrorBff ? e.info : null;
  switch (info?.codigo) {
    case "TIPO_NO_ADMITIDO":
      return "Ese archivo no es un PDF, Word (.docx) o texto (.txt) válido, o su extensión no coincide con su contenido.";
    case "ARCHIVO_DEMASIADO_GRANDE":
      return info.mensaje || "El archivo es demasiado grande.";
    case "REMEDIACION_EN_PROCESO":
      return "Ya hay una evidencia de este control en análisis. Espera su resultado.";
    case "CONTROL_SIN_BRECHA":
      return "Este control ya está cumplido.";
    case "PROMPT_INJECTION":
      return "La justificación tiene instrucciones que no podemos aceptar. Describe solo cómo cumple ahora tu organización.";
    case "LIMITE_EVIDENCIAS":
      return info.mensaje || "Tu empresa alcanzó el máximo de evidencias de hoy.";
    case "CONTRATO_NO_VIGENTE":
      return "El servicio de tu empresa no está activo. Contacta a Therion Labs para renovarlo.";
    case "SESION_EXPIRADA":
      return "Tu sesión terminó. Vuelve a ingresar para seguir.";
    case "SIN_CONEXION":
      return "No pudimos conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.";
    default:
      return info?.mensaje || "No pudimos subir la evidencia. Inténtalo de nuevo.";
  }
}

/* ------------------------------------------------------------ correcciones 05-11 */

/** Cómo va cada dimensión en "Tu madurez ahora": puntaje actual y lo que subió por evidencia. */
export interface AvanceDimension {
  dominio: string;
  puntaje: number;
  meta: number;
  /** Puntos que sumaron al puntaje GENERAL las evidencias de esta dimensión. */
  aporte: number;
  /** Preguntas que mejoraron por evidencia en esta dimensión. */
  mejoradas: number;
  /** Brechas que siguen abiertas en esta dimensión. */
  abiertas: number;
}

/**
 * Une el puntaje actual de cada dimensión con las mejoras por evidencia y las brechas abiertas.
 * Orden: primero donde más subió; luego, las que siguen con más brechas abiertas.
 */
export function avancePorDimension(
  dominios: Pick<DominioVista, "nombre" | "puntaje" | "meta">[],
  evolucion: MejoraRemediacionApi[] | undefined,
  controles: Pick<ControlRemediacionApi, "dominio">[],
): AvanceDimension[] {
  const filas = dominios.map<AvanceDimension>((d) => ({
    dominio: d.nombre, puntaje: d.puntaje, meta: d.meta, aporte: 0, mejoradas: 0,
    abiertas: controles.filter((c) => c.dominio === d.nombre).length,
  }));
  const por = new Map(filas.map((f) => [f.dominio, f]));
  for (const m of evolucion ?? []) {
    const f = m.dominio ? por.get(m.dominio) : undefined;
    if (!f) continue;
    f.aporte = Math.round((f.aporte + (m.despues - m.antes)) * 10) / 10;
    f.mejoradas += 1;
  }
  return filas.sort((a, b) => b.aporte - a.aporte || b.abiertas - a.abiertas || a.puntaje - b.puntaje);
}

/** "La política de uso de IA…" (recorta textos largos del control para listarlos). */
export function recortar(texto: string | null | undefined, max = 90): string {
  const t = (texto ?? "").replace(/\s+/g, " ").trim();
  return t.length <= max ? t : `${t.slice(0, max - 1).trimEnd()}…`;
}

export const etiquetaEstado = (e: string | null | undefined) =>
  e && e in ETIQUETA_ESTADO ? ETIQUETA_ESTADO[e as EstadoClasificacion] : null;
