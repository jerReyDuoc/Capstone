/**
 * HU-21 · Informe del autodiagnóstico para el directorio o un auditor.
 *
 * El PDF lo genera SIEMPRE el servidor (criterio 1). Esta página solo muestra la "ficha"
 * que el backend arma con el mismo cálculo que el PDF (GET /evaluaciones/{id}/informe/ficha):
 * código de evaluación, fechas, versión de la matriz, aviso legal, los 5 puntajes, el
 * resumen de brechas y rutas, y la huella de verificación. Lo que se ve aquí es lo que dirá
 * la portada del PDF; nada se recalcula en el navegador.
 */
import type { PanelVista, Severidad } from "./types";

export interface PuntajeInformeApi {
  nombre: string;
  /** null = la dimensión no tiene preguntas aplicables. */
  puntaje: number | null;
  nivel: string;
  preguntas: number;
  global: boolean;
}

export interface FichaInformeApi {
  evaluacion_id: number;
  /** CIA-AAAA-NNNNNN-D (dígito verificador módulo 11, como el RUT). */
  codigo: string;
  rubro: string | null;
  fecha_evaluacion: string | null;
  fecha_completado: string | null;
  /** "<etiqueta>+<huella de 8 hex>", p. ej. "2026.1+3fa9c2d1". */
  version_matriz: string;
  /** false = evaluación anterior a HU-21: es la versión vigente al emitir, no la registrada. */
  version_matriz_registrada: boolean;
  aviso_legal: {
    version: string;
    titulo: string;
    parrafos: string[];
    pie: string;
    aceptado_version: string | null;
    aceptado_fecha: string | null;
  };
  puntajes: PuntajeInformeApi[];
  meta: number | null;
  brechas: {
    total: number;
    por_severidad: Record<Severidad, number>;
    principales: { prioridad: number; severidad: Severidad; dimension: string; descripcion: string }[];
  };
  rutas: {
    modulos: number;
    horas: number;
    dimensiones: { dimension: string; nivel: string; modulos: number; horas: number }[];
  };
  en_revision: number;
  huella: string;
  /** Primeros 16 hex en grupos de 4: "571D 1A9A C63E 5ADE". */
  huella_corta: string;
  archivo: string;
}

export const META_INFORME_POR_DEFECTO = 75;

/* ------------------------------------------------------------------ código de evaluación */

/** Módulo 11 con la serie 2..7 (igual que el backend, app/application/informes/ficha.py). */
export function digitoVerificador(numero: number): string {
  if (!Number.isInteger(numero) || numero < 0) throw new Error("Número de evaluación inválido");
  let suma = 0;
  let factor = 2;
  for (const d of String(numero).split("").reverse()) {
    suma += Number(d) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const resto = 11 - (suma % 11);
  return resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
}

/** El código está bien formado y su dígito verificador cuadra. */
export function codigoValido(codigo: string): boolean {
  const m = /^CIA-(\d{4})-(\d{6,})-([0-9K])$/.exec((codigo ?? "").trim().toUpperCase());
  return !!m && digitoVerificador(Number(m[2])) === m[3];
}

/* ------------------------------------------------------------------ formatos */

const FORMATO_FECHA = new Intl.DateTimeFormat("es-CL", {
  day: "2-digit", month: "long", year: "numeric", timeZone: "America/Santiago",
});
const FORMATO_FECHA_HORA = new Intl.DateTimeFormat("es-CL", {
  day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  timeZone: "America/Santiago",
});

/**
 * Fechas de la API: "2026-10-30" (día, sin hora) o "2026-11-02T15:30:00" (UTC sin zona).
 * Se muestran en hora de Chile, como el PDF.
 */
export function formatoFechaInforme(iso: string | null | undefined, conHora = false): string {
  if (!iso) return "Sin fecha";
  const soloDia = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  const fecha = new Date(soloDia ? `${iso}T12:00:00Z` : /[zZ]|[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(fecha.getTime())) return "Sin fecha";
  return (conHora && !soloDia ? FORMATO_FECHA_HORA : FORMATO_FECHA).format(fecha);
}

/** La fecha de la evaluación es la de cierre; las antiguas solo tienen la de inicio. */
export function fechaEvaluacion(f: Pick<FichaInformeApi, "fecha_completado" | "fecha_evaluacion">): string {
  return f.fecha_completado ? formatoFechaInforme(f.fecha_completado, true) : formatoFechaInforme(f.fecha_evaluacion);
}

const PLURAL_SEVERIDAD: Record<Severidad, [string, string]> = {
  "Crítica": ["crítica", "críticas"],
  Alta: ["alta", "altas"],
  Media: ["media", "medias"],
  Baja: ["baja", "bajas"],
  "Sin clasificar": ["sin clasificar", "sin clasificar"],
};
const ORDEN_SEVERIDAD: Severidad[] = ["Crítica", "Alta", "Media", "Baja", "Sin clasificar"];

/** "1 crítica, 2 altas y 1 media" (vacío si no hay brechas). */
export function textoSeveridades(por: Partial<Record<Severidad, number>>): string {
  const partes = ORDEN_SEVERIDAD.filter((s) => (por[s] ?? 0) > 0).map(
    (s) => `${por[s]} ${PLURAL_SEVERIDAD[s][(por[s] ?? 0) === 1 ? 0 : 1]}`,
  );
  if (partes.length <= 1) return partes.join("");
  return `${partes.slice(0, -1).join(", ")} y ${partes[partes.length - 1]}`;
}

export const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

/** "55,5" (coma decimal, sin ceros de más) o "—" si no aplica. */
export function formatoPuntajeInforme(p: number | null): string {
  if (p == null) return "—";
  return (Math.round(p * 10) / 10).toLocaleString("es-CL", { maximumFractionDigits: 1 });
}

/** Ancho de la barra 0–100 en % (acotado). */
export const anchoBarra = (p: number | null) => (p == null ? 0 : Math.max(0, Math.min(100, p)));

/* ------------------------------------------------------------------ modo demo */

/** Ficha de ejemplo para NEXT_PUBLIC_DEMO=1 (sin backend). */
export function fichaDemo(panel: PanelVista): FichaInformeApi {
  const anio = new Date().getFullYear();
  const codigo = `CIA-${anio}-${String(panel.evaluacionId).padStart(6, "0")}-${digitoVerificador(panel.evaluacionId)}`;
  const oficiales = ["Gobernanza de IA", "Gestión de Riesgos", "Protección de Datos", "Uso Responsable"];
  const porSev = { "Crítica": 0, Alta: 0, Media: 0, Baja: 0, "Sin clasificar": 0 } as Record<Severidad, number>;
  panel.brechas.forEach((b) => (porSev[b.severidad] += 1));
  return {
    evaluacion_id: panel.evaluacionId,
    codigo,
    rubro: "Retail",
    fecha_evaluacion: new Date().toISOString().slice(0, 10),
    fecha_completado: null,
    version_matriz: "2026.1+demo0000",
    version_matriz_registrada: true,
    aviso_legal: {
      version: "demo",
      titulo: "Aviso legal",
      parrafos: [
        "Modo demo: con el backend conectado aquí aparece el texto vigente del aviso legal, el mismo que imprime el PDF.",
      ],
      pie: "Autodiagnóstico orientativo: no certifica el cumplimiento de la Ley N.º 21.719 ni constituye asesoría legal.",
      aceptado_version: null,
      aceptado_fecha: null,
    },
    puntajes: [
      { nombre: "Global", puntaje: panel.puntajeGeneral, nivel: "—", preguntas: panel.controlesEvaluados, global: true },
      ...oficiales.map((nombre) => {
        const d = panel.dominios.find((x) => x.nombre === nombre);
        return { nombre, puntaje: d?.puntaje ?? null, nivel: d ? "—" : "Sin preguntas aplicables", preguntas: d?.controles ?? 0, global: false };
      }),
    ],
    meta: panel.meta,
    brechas: {
      total: panel.brechas.length,
      por_severidad: porSev,
      principales: panel.brechas.slice(0, 3).map((b) => ({
        prioridad: b.prioridad, severidad: b.severidad, dimension: b.dominio, descripcion: b.descripcion,
      })),
    },
    rutas: { modulos: 0, horas: 0, dimensiones: [] },
    en_revision: panel.enRevision,
    huella: "0".repeat(64),
    huella_corta: "0000 0000 0000 0000",
    archivo: `informe_evaluacion-${panel.evaluacionId}.pdf`,
  };
}
