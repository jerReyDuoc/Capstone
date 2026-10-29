/**
 * HU-28 · Espacio de la empresa del usuario definitivo (navegador → /bff/cliente/api/*).
 * Refleja GET /api/cliente/empresa (app/api/routes/cliente.py).
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";

export interface EvaluacionEmpresa {
  id: number;
  estado_progreso: string | null;
  completada: boolean;
  fecha_inicio: string | null;
  fecha_migracion: string | null;
  puntaje_general: number | null;
}

export interface EspacioEmpresaApi {
  usuario: { nombre: string; email: string };
  empresa: {
    id: number;
    razon_social: string;
    rut: string;
    rubro: string | null;
    fecha_inicio_contrato: string;
    fecha_termino_contrato: string;
    contrato_vigente: boolean;
    contrato?: ContratoApi;
  };
  evaluaciones: EvaluacionEmpresa[];
}

/** HU-30 · situación del contrato (app/domain/contrato.py). */
export type SituacionContrato = "pendiente" | "vigente" | "suspendido" | "vencido" | "terminado" | "finalizado";

export interface ContratoApi {
  estado: "activo" | "suspendido" | "terminado";
  situacion: SituacionContrato;
  fecha_inicio_contrato: string;
  fecha_termino_contrato: string;
  servicio_habilitado: boolean;
  documentos_disponibles: boolean;
  en_plazo_de_gracia: boolean;
  documentos_disponibles_hasta: string | null;
  mensaje: string;
}

/** HU-30 · GET /api/cliente/contrato: lo que el usuario puede hacer sin servicio pagado. */
export interface ContratoClienteApi {
  empresa: { id: number; razon_social: string };
  contrato: ContratoApi;
  documentos: {
    constancias: { ruta_id: number; modulo: string; fecha_completado: string | null; codigo: string }[];
    evaluaciones: { id: number; completada: boolean }[];
  };
  arcop: { disponible: boolean };
}

export const BASE_CLIENTE = "/bff/cliente/api";

export const cargarEspacioEmpresa = () => pedir<EspacioEmpresaApi>(`${BASE_CLIENTE}/cliente/empresa`);
export const cargarContratoCliente = () => pedir<ContratoClienteApi>(`${BASE_CLIENTE}/cliente/contrato`);

/** HU-30: códigos con que el backend corta el servicio pagado. */
export const SIN_SERVICIO = new Set(["CONTRATO_NO_VIGENTE", "PLAZO_GRACIA_VENCIDO"]);

/** Días que faltan para el término del contrato (negativo si ya terminó). */
export function diasParaTermino(terminoISO: string, hoy = new Date()): number {
  const [a, m, d] = terminoISO.slice(0, 10).split("-").map(Number);
  const fin = Date.UTC(a, m - 1, d);
  const inicioHoy = Date.UTC(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return Math.round((fin - inicioHoy) / 86_400_000);
}

/** "2026-10-27" → "27-10-2026" sin pasar por la zona horaria del navegador. */
export function fechaCorta(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return a && m && d ? `${d}-${m}-${a}` : "—";
}

/* ============================================================ HU-29 */
/* GET /api/cliente/evaluaciones · "Mis evaluaciones" (app/application/informes/historial.py) */

export interface NivelApi {
  codigo: "inicial" | "en_desarrollo" | "gestionado" | "optimizado";
  etiqueta: string;
}

export interface DimensionHistorial {
  dominio_id: number;
  dominio: string;
  puntaje: number | null;
  nivel: string | null;
}

export interface EvaluacionHistorial {
  id: number;
  /** "migrada" = viene del autodiagnóstico; "reevaluacion" = iniciada desde la cuenta. */
  tipo: "migrada" | "reevaluacion";
  origen: string | null;
  estado_progreso: string | null;
  completada: boolean;
  /** Día de referencia: cuando se completó (o, en las antiguas, cuando se inició). */
  fecha: string | null;
  fecha_inicio: string | null;
  fecha_completado: string | null;
  fecha_migracion: string | null;
  puntaje_global: number | null;
  nivel: NivelApi | null;
  /** Diferencia con la evaluación completada anterior (null en la primera). */
  variacion: number | null;
  /** La completada más reciente: la que cuenta para el benchmark, la formación y el tutor. */
  vigente: boolean;
  dimensiones: DimensionHistorial[];
}

export interface PuntoEvolucion {
  evaluacion_id: number;
  fecha: string | null;
  puntaje: number | null;
}

export interface HistorialApi {
  empresa: { id: number; razon_social: string };
  resumen: {
    total: number;
    completadas: number;
    evaluacion_vigente_id: number | null;
    evaluacion_en_curso_id: number | null;
    puntaje_actual: number | null;
    nivel_actual: NivelApi | null;
    variacion_total: number | null;
  };
  evaluaciones: EvaluacionHistorial[];
  evolucion: {
    global: (PuntoEvolucion & { nivel: NivelApi | null })[];
    dimensiones: { dominio_id: number; dominio: string; puntos: PuntoEvolucion[] }[];
  };
  puede_reevaluar: boolean;
  servicio_habilitado: boolean;
}

export const cargarHistorial = () => pedir<HistorialApi>(`${BASE_CLIENTE}/cliente/evaluaciones`);

/** 201 con la evaluación nueva; 409 EVALUACION_EN_CURSO trae detail.evaluacion_id para retomarla. */
export const iniciarReevaluacion = () =>
  pedir<{ evaluacion_id: number; estado_progreso: string }>(`${BASE_CLIENTE}/cliente/evaluaciones`, { method: "POST", json: {} });

/**
 * Colores de las dimensiones en el gráfico de evolución (components/charts/EvolucionMadurez.tsx).
 * Categórica para el fondo oscuro (#0a100e), en orden fijo: azul, naranja, violeta, ámbar,
 * magenta. Validada con el script de dataviz (banda de luminosidad, croma, separación CVD ≥ 8 y
 * visión normal ≥ 15 entre adyacentes, contraste ≥ 3:1). El verde de marca queda para la serie global.
 */
export const COLORES_DIMENSION = ["#3987e5", "#d95926", "#9085e9", "#c98500", "#d55181"] as const;

/* GET /api/cliente/documentos · "Mis documentos" (app/application/use_cases/documentos_empresa.py) */

export interface DocumentoGenerado {
  id: number;
  tipo: "informe_pdf" | "borrador";
  nombre: string;
  evaluacion_id: number | null;
  mime_type: string;
  tamano_bytes: number;
  fecha_creacion: string;
}

export interface EvidenciaDocumento {
  id: number;
  nombre: string;
  evaluacion_id: number;
  control: string | null;
  origen: "cuestionario" | "remediacion" | string;
  fecha_subida: string | null;
  estado_validacion: string;
  clasificacion: string | null;
  en_proceso: boolean;
}

export interface ConstanciaDocumento {
  ruta_id: number;
  modulo: string;
  fecha_completado: string | null;
  codigo: string;
}

export interface DocumentosApi {
  empresa: { id: number; razon_social: string };
  informes: DocumentoGenerado[];
  borradores: DocumentoGenerado[];
  evidencias: EvidenciaDocumento[];
  constancias: ConstanciaDocumento[];
  documentos_disponibles_hasta: string | null;
}

export type TipoEliminable = "documento" | "evidencia" | "constancia";

export const cargarDocumentos = () => pedir<DocumentosApi>(`${BASE_CLIENTE}/cliente/documentos`);

export const archivarInforme = (evaluacionId: number) =>
  pedir<DocumentoGenerado>(`${BASE_CLIENTE}/cliente/documentos/informes`, { method: "POST", json: { evaluacion_id: evaluacionId } });

/** Ruta del BFF para descargar o eliminar cada tipo de documento. */
export function rutaDocumento(tipo: TipoEliminable, id: number, accion: "descarga" | "eliminar"): string {
  const base = `${BASE_CLIENTE}/cliente/documentos`;
  if (tipo === "constancia") {
    return accion === "descarga" ? `${BASE_CLIENTE}/formacion/modulos/${id}/constancia` : `${base}/constancias/${id}`;
  }
  const raiz = tipo === "evidencia" ? `${base}/evidencias/${id}` : `${base}/${id}`;
  return accion === "descarga" ? `${raiz}/descarga` : raiz;
}

export const eliminarDocumento = (tipo: TipoEliminable, id: number) =>
  pedir<void>(rutaDocumento(tipo, id, "eliminar"), { method: "DELETE" });

/** Nombre del archivo desde Content-Disposition (solo [\w.-], como lo arma el backend). */
export function nombreDesdeDisposicion(disposicion: string | null, porDefecto: string): string {
  const m = /filename="?([\w.-]+)"?/i.exec(disposicion ?? "");
  return m?.[1] ?? porDefecto;
}

export async function descargarDocumento(tipo: TipoEliminable, id: number): Promise<{ blob: Blob; nombre: string }> {
  const res = await fetch(rutaDocumento(tipo, id, "descarga"), { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let info = { codigo: `HTTP_${res.status}`, mensaje: "" };
    try {
      info = ((await res.json()) as { error: typeof info }).error ?? info;
    } catch {
      /* sin cuerpo */
    }
    throw new ErrorBff(res.status, info);
  }
  return { blob: await res.blob(), nombre: nombreDesdeDisposicion(res.headers.get("content-disposition"), `documento-${id}`) };
}

/** "1 234 KB" legible. */
export function tamanoLegible(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

/** "+12,5" / "−3" / "sin cambio" para la variación del puntaje global. */
export function textoVariacion(v: number | null | undefined): string {
  if (v == null) return "—";
  if (Math.abs(v) < 0.05) return "sin cambio";
  const n = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1 }).format(Math.abs(v));
  return v > 0 ? `+${n}` : `−${n}`;
}
