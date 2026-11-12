/**
 * Informe del registro de actividades de tratamiento (navegador → /bff/cliente/api/registro-actividades/informes).
 *
 * El servidor arma el PDF y la planilla Excel desde la versión vigente de cada actividad, les pone el mismo
 * código verificable, los guarda en "Mis documentos" y deja cada descarga en el registro de auditoría. Aquí
 * van las llamadas y la lógica pura de presentación (probada en tests/informe_rat.test.ts):
 *   - la validación del código verificable antes de consultarlo (el último carácter es de control);
 *   - los textos del estado del informe (oficial o borrador) y de los niveles de riesgo.
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import { nombreDesdeDisposicion } from "@/lib/empresa";

export const BASE_INFORME_RAT = "/bff/cliente/api/registro-actividades/informes";

export type FormatoInforme = "pdf" | "xlsx";
export type NivelRiesgo = "Bajo" | "Medio" | "Alto" | "Crítico";

export interface ResumenInforme {
  actividades: number;
  archivadas_excluidas: number;
  por_estado: { vigente: number; en_revision: number; borrador: number };
  sin_version_vigente: number;
  con_sensibles: number;
  categorias_sensibles: string[];
  con_nna: number;
  transferencias: number;
  transferencias_sin_garantia: number;
  actividades_con_transferencias: number;
  paises_destino: string[];
  con_decisiones: number;
  con_perfilamiento: number;
  decisiones_sin_revision_humana: number;
  terceros: number;
  terceros_sin_contrato: number;
  como_encargado: number;
  bases_licitud: Record<string, number>;
  riesgos: Record<NivelRiesgo, number>;
  riesgos_altos: number;
}

export interface ActividadPrevia {
  id: number;
  numero: number;
  nombre: string;
  estado: "borrador" | "en_revision" | "vigente";
  estado_nombre: string;
  origen: "vigente" | "trabajo";
  version: number | null;
  pendiente: string | null;
  riesgo: { nivel: NivelRiesgo; puntaje: number; probabilidad: number; impacto: number } | null;
}

export interface PreviaInforme {
  borrador: boolean;
  motivos_borrador: string[];
  huella: string;
  resumen: ResumenInforme;
  actividades: ActividadPrevia[];
  /** Conteo por celda: filas = probabilidad 5→1, columnas = impacto 1→5. */
  mapa_calor: number[][];
  aviso: { version: string; pie: string };
  puede_emitir: boolean;
  version_siguiente: number;
}

export interface DocumentoEmision {
  id: number;
  nombre: string;
  tamano_bytes: number;
}

export interface EmisionInforme {
  id: number;
  codigo: string;
  version_rat: number;
  fecha: string;
  borrador: boolean;
  motivos_borrador: string[];
  actividades: number;
  huella: string;
  huella_legible: string;
  resumen: Partial<ResumenInforme>;
  aviso_version: string;
  documentos: { pdf: DocumentoEmision | null; xlsx: DocumentoEmision | null };
}

export interface ListaInformes {
  previa: PreviaInforme;
  al_dia: boolean;
  ultima: EmisionInforme | null;
  emisiones: EmisionInforme[];
  limites: { emisiones_dia: number; correos_dia: number };
  correo_habilitado: boolean;
}

export interface RespuestaEmision {
  informe: EmisionInforme;
  reutilizado: boolean;
  mensaje: string;
}

export interface RespuestaVerificacion {
  valido: boolean;
  informe: EmisionInforme;
  sigue_al_dia: boolean;
  mensaje: string;
}

/* ============================================================ llamadas */

export const cargarInformes = () => pedir<ListaInformes>(BASE_INFORME_RAT);

export const emitirInforme = (forzar = false) =>
  pedir<RespuestaEmision>(BASE_INFORME_RAT, { method: "POST", json: { forzar } });

export const enviarInforme = (id: number, email: string, formatos: FormatoInforme[]) =>
  pedir<{ enviado: boolean; destino: string; modo: string; formatos: FormatoInforme[] }>(`${BASE_INFORME_RAT}/${id}/enviar`, {
    method: "POST",
    json: { ...(email.trim() ? { email: email.trim() } : {}), formatos },
  });

export const verificarCodigo = (codigo: string) =>
  pedir<RespuestaVerificacion>(`${BASE_INFORME_RAT}/verificacion?codigo=${encodeURIComponent(normalizarCodigo(codigo))}`);

export async function descargarInforme(id: number, formato: FormatoInforme): Promise<{ blob: Blob; nombre: string }> {
  const res = await fetch(`${BASE_INFORME_RAT}/${id}/descarga?formato=${formato}`, { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let info = { codigo: `HTTP_${res.status}`, mensaje: "" };
    try {
      info = ((await res.json()) as { error: typeof info }).error ?? info;
    } catch {
      /* sin cuerpo */
    }
    throw new ErrorBff(res.status, info);
  }
  return {
    blob: await res.blob(),
    nombre: nombreDesdeDisposicion(res.headers.get("content-disposition"), `registro_actividades.${formato}`),
  };
}

/* ============================================================ código verificable */

const PREFIJO = "CIA-REG";

/** Mayúsculas y sin espacios: "cia-reg-2026-000045-k " → "CIA-REG-2026-000045-K". */
export function normalizarCodigo(codigo: string): string {
  return codigo.trim().toUpperCase().replace(/\s+/g, "");
}

/** Dígito verificador módulo 11 con la serie 2..7 (como el RUT): 0-9 o K. */
export function digitoVerificador(numero: number): string {
  let suma = 0;
  let factor = 2;
  for (const d of String(numero).split("").reverse()) {
    suma += Number(d) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const resto = 11 - (suma % 11);
  return resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
}

/** null si el código parece válido; si no, qué está mal (para avisar antes de consultar al servidor). */
export function problemaCodigo(codigo: string): string | null {
  const c = normalizarCodigo(codigo);
  if (!c) return "Escribe el código que aparece en la portada del informe.";
  const m = new RegExp(`^${PREFIJO}-(\\d{4})-(\\d{6,9})-([0-9K])$`).exec(c);
  if (!m) return "El código debe tener la forma CIA-REG-2026-000045-K.";
  if (digitoVerificador(Number(m[2])) !== m[3]) return "El último carácter no coincide: revisa que el código esté bien copiado.";
  return null;
}

/* ============================================================ textos */

export const TONO_NIVEL: Record<NivelRiesgo, string> = {
  Bajo: "var(--bajo)",
  Medio: "var(--medio)",
  Alto: "var(--naranja)",
  Crítico: "var(--critico)",
};

export const ETIQUETA_PROBABILIDAD = ["", "Muy baja", "Baja", "Media", "Alta", "Muy alta"];
export const ETIQUETA_IMPACTO = ["", "Muy bajo", "Bajo", "Moderado", "Alto", "Muy alto"];

/** Nivel de una celda de la matriz (probabilidad × impacto). */
export function nivelDe(puntaje: number): NivelRiesgo {
  if (puntaje <= 4) return "Bajo";
  if (puntaje <= 9) return "Medio";
  if (puntaje <= 14) return "Alto";
  return "Crítico";
}

export const NOMBRE_FORMATO: Record<FormatoInforme, string> = { pdf: "PDF", xlsx: "Excel" };

/** Para el botón principal: qué va a pasar al generar. */
export function textoAccionInforme(l: Pick<ListaInformes, "al_dia" | "ultima" | "previa">): string {
  if (!l.previa.puede_emitir) return "Registra al menos una actividad";
  if (l.al_dia && l.ultima) return "Descargar el informe al día";
  return l.previa.borrador ? "Generar informe (borrador)" : "Generar informe oficial";
}
