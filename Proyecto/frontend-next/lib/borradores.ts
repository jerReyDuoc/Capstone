/**
 * HU-16 · Borradores de cumplimiento (navegador → /bff/cliente/api/borradores).
 *
 * El backend arma el borrador con la plantilla (Política de uso de LLM, Aviso de privacidad,
 * PIA), la evaluación más reciente de la empresa y, si se pide, el Agente IA. Aquí solo hay
 * llamadas y lógica de presentación pura (probada en tests/hu16_borradores.test.ts):
 *   - la vista previa del Markdown se arma como BLOQUES y SEGMENTOS que React pinta como
 *     texto (nunca innerHTML): lo que escribe el usuario no puede inyectar HTML;
 *   - los marcadores [COMPLETAR: ...] pendientes, para ubicarlos en el editor.
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";

export const BASE_BORRADORES = "/bff/cliente/api/borradores";

export type TipoBorrador = "politica_llm" | "aviso_privacidad" | "pia";
export type EstadoBorrador = "en_revision" | "consolidado";
export type FormatoBorrador = "md" | "pdf";

export interface PlantillaApi {
  tipo: TipoBorrador;
  titulo: string;
  descripcion: string;
  secciones: string[];
  dimensiones: string[];
  version: string;
}

export interface CuotaBorradoresApi {
  usados: number;
  limite: number | null;
  restantes: number | null;
  reinicia_en: string;
}

/** Actividad del registro que puede entrar en la evaluación de impacto. */
export interface ActividadRegistroBorrador {
  actividad_id: number;
  nombre: string;
  nivel: "Bajo" | "Medio" | "Alto" | "Crítico";
  puntaje: number;
  requiere_pia: boolean;
  motivos_pia: string[];
  vigente: boolean;
}

export interface CatalogoBorradoresApi {
  /** Lo que la evaluación de impacto y el aviso de privacidad toman del registro de actividades. */
  registro?: { actividades: ActividadRegistroBorrador[]; pia: ActividadRegistroBorrador[]; finalidades: number };
  plantillas: PlantillaApi[];
  ia_habilitada: boolean;
  cuota: CuotaBorradoresApi;
  max_caracteres_contenido: number;
  max_caracteres_instrucciones: number;
  max_en_revision: number;
}

export interface BorradorApi {
  id: number;
  tipo: TipoBorrador;
  titulo: string;
  estado: EstadoBorrador;
  version: number;
  editable: boolean;
  adaptado_ia: boolean;
  evaluacion_id: number | null;
  version_plantillas: string;
  pendientes: number;
  notas: string[];
  advertencias: string[];
  fecha_creacion: string;
  fecha_actualizacion: string;
  fecha_consolidacion: string | null;
  documento_id: number | null;
  /** Solo en el detalle (GET /borradores/{id}, generar, editar y consolidar). */
  contenido?: string;
  pendientes_detalle?: string[];
}

export interface GenerarBorradorApi {
  borrador: BorradorApi;
  cuota: CuotaBorradoresApi;
  /** El borrador se armó sin el Agente IA (deshabilitado, cuota agotada o no respondió). */
  aviso?: string;
  /** Actividades del registro que usó (evaluación de impacto y aviso de privacidad). */
  registro?: { actividades: number; ids: number[]; sin_version_vigente: number };
}

/* ------------------------------------------------------------ llamadas */

export const cargarCatalogoBorradores = () => pedir<CatalogoBorradoresApi>(`${BASE_BORRADORES}/plantillas`);

export const listarBorradores = () => pedir<{ items: BorradorApi[] }>(BASE_BORRADORES);

/** Nunca se reintenta: puede llamar al LLM y gastar cuota. */
export const generarBorrador = (tipo: TipoBorrador, instrucciones: string, usarIa: boolean, actividades: number[] = []) =>
  pedir<GenerarBorradorApi>(BASE_BORRADORES, {
    method: "POST",
    json: {
      tipo, instrucciones: instrucciones.trim() || null, usar_ia: usarIa,
      ...(tipo === "pia" && actividades.length ? { actividades: actividades.slice(0, MAX_ACTIVIDADES_PIA) } : {}),
    },
  });

/** Máximo de actividades del registro en una evaluación de impacto (igual que el backend). */
export const MAX_ACTIVIDADES_PIA = 10;

/**
 * Actividades que la evaluación de impacto marca de entrada: la pedida por la URL (si existe en el registro)
 * o las que tienen la evaluación recomendada.
 */
export function actividadesPiaIniciales(
  registro: CatalogoBorradoresApi["registro"] | undefined,
  pedida: number | null,
): number[] {
  if (!registro) return [];
  if (pedida && registro.actividades.some((a) => a.actividad_id === pedida)) return [pedida];
  return registro.pia.map((a) => a.actividad_id).slice(0, MAX_ACTIVIDADES_PIA);
}

/** Qué tomará del registro cada plantilla (texto de ayuda bajo el formulario). */
export function textoRegistroBorrador(
  tipo: TipoBorrador,
  registro: CatalogoBorradoresApi["registro"] | undefined,
  elegidas: number,
): string | null {
  if (tipo === "politica_llm") return null;
  if (!registro || !registro.actividades.length) {
    return "Tu registro de actividades está vacío: el borrador saldrá con la plantilla. Completa el registro para que tome tus finalidades, bases y riesgos.";
  }
  if (tipo === "aviso_privacidad") {
    return `Tomará las ${registro.finalidades} finalidades de tu registro con su base de licitud, los datos, proveedores, transferencias y plazos.`;
  }
  if (!elegidas) {
    return "Ninguna actividad tiene una evaluación de impacto recomendada. Elige alguna para pre-llenarla o genera la plantilla en blanco.";
  }
  return `Se pre-llenará con ${elegidas === 1 ? "1 actividad" : `${elegidas} actividades`} de tu registro: descripción, base de licitud, riesgos y medidas.`;
}

export const cargarBorrador = (id: number) => pedir<{ borrador: BorradorApi }>(`${BASE_BORRADORES}/${id}`);

export const guardarBorrador = (id: number, contenido: string, version: number) =>
  pedir<{ borrador: BorradorApi }>(`${BASE_BORRADORES}/${id}`, { method: "PATCH", json: { contenido, version } });

export const consolidarBorrador = (id: number, version: number, confirmarPendientes: boolean) =>
  pedir<{ borrador: BorradorApi; documento: { id: number; nombre: string } }>(`${BASE_BORRADORES}/${id}/consolidacion`, {
    method: "POST",
    json: { version, confirmar_pendientes: confirmarPendientes },
  });

export const descartarBorrador = (id: number) => pedir<void>(`${BASE_BORRADORES}/${id}`, { method: "DELETE" });

export function rutaDescargaBorrador(id: number, formato: FormatoBorrador): string {
  return `${BASE_BORRADORES}/${id}/descarga?formato=${formato}`;
}

export async function descargarBorrador(id: number, formato: FormatoBorrador): Promise<{ blob: Blob; nombre: string }> {
  const res = await fetch(rutaDescargaBorrador(id, formato), { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let info = { codigo: `HTTP_${res.status}`, mensaje: "" };
    try {
      info = ((await res.json()) as { error: typeof info }).error ?? info;
    } catch {
      /* sin cuerpo */
    }
    throw new ErrorBff(res.status, info);
  }
  const m = /filename="?([\w.-]+)"?/i.exec(res.headers.get("content-disposition") ?? "");
  return { blob: await res.blob(), nombre: m?.[1] ?? `borrador-${id}.${formato}` };
}

/* ------------------------------------------------------------ presentación */

export const ETIQUETA_TIPO: Record<TipoBorrador, string> = {
  politica_llm: "Política de uso de LLM",
  aviso_privacidad: "Aviso de privacidad",
  pia: "Evaluación de impacto (PIA)",
};

export const ETIQUETA_ESTADO: Record<EstadoBorrador, { texto: string; tono: "medio" | "ok" }> = {
  en_revision: { texto: "En revisión", tono: "medio" },
  consolidado: { texto: "Consolidado", tono: "ok" },
};

/**
 * Advertencias de la generación que le sirven al usuario (las demás son de auditoría).
 * Los avisos de "sin IA" ya llegan como `aviso` al generar; aquí se repiten al reabrir.
 */
const TEXTO_ADVERTENCIA: Record<string, string> = {
  ia_deshabilitada: "Se armó sin el Agente IA (no está habilitado).",
  cuota_ia_agotada: "Se armó sin el Agente IA: tu empresa usó la cuota diaria de borradores con IA.",
  ia_no_disponible: "Se armó sin el Agente IA: el servicio no respondió.",
  salida_ia_descartada: "Descartamos lo que propuso el Agente IA porque no pasó la validación de seguridad.",
  articulo_no_verificado: "Descartamos secciones del Agente IA que citaban artículos no verificados.",
  codigo: "Quitamos contenido técnico que no corresponde a un documento.",
  url: "Quitamos enlaces externos que propuso el Agente IA.",
  registro_aplicado: "Completamos secciones con tu registro de actividades: revísalas antes de aprobar.",
  registro_no_vigente: "Algunas actividades que usamos aún no están vigentes en tu registro.",
  registro_vacio: "Tu registro de actividades está vacío: el borrador salió con la plantilla.",
  pia_sin_alto_riesgo: "Ninguna actividad de tu registro tiene una evaluación de impacto recomendada.",
};

export function advertenciasVisibles(codigos: readonly string[]): string[] {
  return [...new Set(codigos.map((c) => TEXTO_ADVERTENCIA[c]).filter((t): t is string => Boolean(t)))];
}

const PENDIENTE = /\[COMPLETAR:[^\]\n]{0,200}\]/g;

/** Marcadores [COMPLETAR: ...] sin repetir, en orden de aparición (igual que el backend). */
export function pendientesDe(markdown: string): string[] {
  return [...new Set(markdown.match(PENDIENTE) ?? [])];
}

/** Posición del siguiente marcador pendiente desde `desde` (para seleccionarlo en el editor). */
export function siguientePendiente(markdown: string, desde = 0): { inicio: number; fin: number } | null {
  const re = new RegExp(PENDIENTE.source, "g");
  re.lastIndex = Math.max(0, desde);
  const m = re.exec(markdown) ?? (desde > 0 ? new RegExp(PENDIENTE.source, "g").exec(markdown) : null);
  return m ? { inicio: m.index, fin: m.index + m[0].length } : null;
}

export interface ValidacionContenido {
  ok: boolean;
  motivo?: string;
}

export function validarContenido(texto: string, max: number): ValidacionContenido {
  if (!texto.trim()) return { ok: false, motivo: "El borrador no puede quedar vacío." };
  if (texto.length > max) return { ok: false, motivo: `El borrador supera los ${max.toLocaleString("es-CL")} caracteres.` };
  return { ok: true };
}

/* ------------------------------------------------------------ vista previa (Markdown seguro) */

export type Segmento =
  | { tipo: "texto"; texto: string }
  | { tipo: "negrita"; texto: string }
  | { tipo: "cursiva"; texto: string }
  | { tipo: "codigo"; texto: string }
  | { tipo: "pendiente"; texto: string };

export type BloqueMd =
  | { tipo: "titulo"; nivel: 1 | 2 | 3; texto: string }
  | { tipo: "parrafo"; texto: string }
  | { tipo: "lista"; ordenada: boolean; items: string[] }
  | { tipo: "cita"; texto: string }
  | { tipo: "tabla"; cabecera: string[]; filas: string[][] }
  | { tipo: "separador" };

const SEP_TABLA = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
const NUMERADA = /^\s*\d{1,3}[.)]\s+(.*)$/;
const VINETA = /^\s*[-*•]\s+(.*)$/;
const TITULO = /^(#{1,3})\s+(.*)$/;

function celdas(linea: string): string[] {
  let s = linea.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

/** El mismo subconjunto de Markdown que el PDF del backend (pdf_borrador.py). */
export function parsearMarkdown(markdown: string): BloqueMd[] {
  const lineas = markdown.replace(/\r\n?/g, "\n").split("\n");
  const bloques: BloqueMd[] = [];
  let parrafo: string[] = [];
  const cerrar = () => {
    if (parrafo.length) bloques.push({ tipo: "parrafo", texto: parrafo.join(" ") });
    parrafo = [];
  };
  let i = 0;
  while (i < lineas.length) {
    const linea = lineas[i];
    const s = linea.trim();
    let m: RegExpExecArray | null;
    if (!s) {
      cerrar();
      i++;
    } else if ((m = TITULO.exec(s))) {
      cerrar();
      bloques.push({ tipo: "titulo", nivel: m[1].length as 1 | 2 | 3, texto: m[2].trim() });
      i++;
    } else if (s === "---" || s === "***" || s === "___") {
      cerrar();
      bloques.push({ tipo: "separador" });
      i++;
    } else if (s.startsWith("|") && i + 1 < lineas.length && SEP_TABLA.test(lineas[i + 1])) {
      cerrar();
      const cabecera = celdas(s);
      const filas: string[][] = [];
      i += 2;
      while (i < lineas.length && lineas[i].trim().startsWith("|")) {
        filas.push(celdas(lineas[i]));
        i++;
      }
      bloques.push({ tipo: "tabla", cabecera, filas });
    } else if (s.startsWith(">")) {
      cerrar();
      const cita: string[] = [];
      while (i < lineas.length && lineas[i].trim().startsWith(">")) {
        const t = lineas[i].trim().slice(1).trim();
        if (t) cita.push(t);
        i++;
      }
      bloques.push({ tipo: "cita", texto: cita.join(" ") });
    } else if ((m = VINETA.exec(linea)) || (m = NUMERADA.exec(linea))) {
      cerrar();
      const ordenada = NUMERADA.test(linea) && !VINETA.test(linea);
      const items: string[] = [];
      while (i < lineas.length) {
        const v = ordenada ? NUMERADA.exec(lineas[i]) : VINETA.exec(lineas[i]);
        if (!v) break;
        items.push(v[1].trim());
        i++;
      }
      bloques.push({ tipo: "lista", ordenada, items });
    } else {
      parrafo.push(s);
      i++;
    }
  }
  cerrar();
  return bloques;
}

const EN_LINEA = /(\[COMPLETAR:[^\]\n]{0,200}\])|\*\*([^*\n]+?)\*\*|(?<![*\w])\*([^*\n]+?)\*(?![*\w])|`([^`\n]{1,200})`/g;

/** Negrita, cursiva, código y marcadores pendientes. Todo lo demás queda como texto. */
export function segmentos(texto: string): Segmento[] {
  const salida: Segmento[] = [];
  let ultimo = 0;
  for (const m of texto.matchAll(EN_LINEA)) {
    const i = m.index ?? 0;
    if (i > ultimo) salida.push({ tipo: "texto", texto: texto.slice(ultimo, i) });
    if (m[1]) salida.push({ tipo: "pendiente", texto: m[1] });
    else if (m[2]) salida.push({ tipo: "negrita", texto: m[2] });
    else if (m[3]) salida.push({ tipo: "cursiva", texto: m[3] });
    else salida.push({ tipo: "codigo", texto: m[4] });
    ultimo = i + m[0].length;
  }
  if (ultimo < texto.length) salida.push({ tipo: "texto", texto: texto.slice(ultimo) });
  return salida;
}

/** "Quedan 3 borradores con IA hoy" (o nada si no hay límite). */
export function cuotaBorradoresTexto(c: CuotaBorradoresApi | null | undefined): string {
  if (!c || c.limite == null || c.restantes == null) return "";
  if (c.restantes === 0) return "Tu empresa usó los borradores con IA de hoy: los nuevos se arman con la plantilla.";
  return `Quedan ${c.restantes} de ${c.limite} borradores con IA hoy.`;
}
