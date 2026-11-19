/**
 * Mejoras 19-11 · Generador de reportes y documentos (/empresa/borradores).
 *
 * Lógica pura (probada en tests/mejoras_1911.test.ts):
 *   - qué documento ayuda a cerrar cada brecha del Plan de acción (según el control);
 *   - la relación brecha → documento generado, que se ve en el historial;
 *   - el catálogo de REPORTES que la plataforma ya genera en otras secciones;
 *   - textos de estado y formato del historial.
 *
 * La relación brecha → documento se guarda en el navegador (como las vistas fijadas del
 * Diagnóstico): el backend aún no la registra. Se borra al cerrar sesión (lib/sesionNavegador.ts).
 */
import type { EstadoBorrador, TipoBorrador } from "./borradores";
import type { BrechaVista } from "./types";

/* ------------------------------------------------------------ brecha → documento */

/**
 * Controles que cada plantilla trata (backend: app/application/borradores/plantillas_borrador.py).
 * Cuando un control aparece en varias, se elige la plantilla más específica para cerrarlo.
 */
const PLANTILLA_POR_CONTROL: Record<string, TipoBorrador> = {
  // Evaluación de impacto: la EIPD y el análisis y tratamiento de riesgos
  "DAT-002": "pia", "RIE-001": "pia", "RIE-003": "pia", "RIE-005": "pia",
  // Aviso de privacidad: transparencia, derechos, bases de licitud, encargados y transferencias
  "DAT-001": "aviso_privacidad", "DAT-003": "aviso_privacidad", "DAT-004": "aviso_privacidad",
  "DAT-005": "aviso_privacidad", "DAT-007": "aviso_privacidad", "DAT-008": "aviso_privacidad",
  "DAT-009": "aviso_privacidad", "DAT-010": "aviso_privacidad", "SEG-008": "aviso_privacidad",
};

/** Por familia de control, si el control no está en la tabla. */
const PLANTILLA_POR_FAMILIA: Record<string, TipoBorrador> = {
  DAT: "aviso_privacidad",
  RIE: "politica_llm",
  GOB: "politica_llm",
  SEG: "politica_llm",
};

/** Plantilla que ayuda a cerrar la brecha (la política de uso de IA cubre el resto de los controles). */
export function plantillaParaBrecha(b: Pick<BrechaVista, "controlCodigo" | "codigo">): TipoBorrador {
  const codigo = (b.controlCodigo ?? b.codigo ?? "").toUpperCase().replace(/^ERR-/, "");
  return PLANTILLA_POR_CONTROL[codigo] ?? PLANTILLA_POR_FAMILIA[codigo.slice(0, 3)] ?? "politica_llm";
}

/** Lo que se recuerda de la brecha para mostrarlo junto al documento. Sin datos personales: texto del catálogo. */
export interface BrechaRelacionada {
  respuestaId: number;
  evaluacionId: number;
  prioridad: number;
  descripcion: string;
}

export const PREFIJO_ALMACEN_DOCUMENTOS = "complianceai.documentos-brecha.";
/** sessionStorage: la brecha desde la que se llegó al generador (pestaña actual). */
export const CLAVE_BRECHA_PENDIENTE = `${PREFIJO_ALMACEN_DOCUMENTOS}pendiente`;
/** localStorage: borrador → brecha (historial). */
export const CLAVE_RELACIONES = `${PREFIJO_ALMACEN_DOCUMENTOS}relaciones.v1`;
export const MAX_RELACIONES = 60;
const MAX_DESCRIPCION = 240;

export function hrefGenerarDocumento(b: Pick<BrechaVista, "respuestaId" | "controlCodigo" | "codigo">, evaluacionId: number): string {
  const q = new URLSearchParams({ plantilla: plantillaParaBrecha(b), brecha: String(b.respuestaId), evaluacion: String(evaluacionId) });
  return `/empresa/borradores?${q.toString()}`;
}

export function relacionDesdeBrecha(b: Pick<BrechaVista, "respuestaId" | "prioridad" | "descripcion">, evaluacionId: number): BrechaRelacionada {
  return { respuestaId: b.respuestaId, evaluacionId, prioridad: b.prioridad, descripcion: b.descripcion.slice(0, MAX_DESCRIPCION) };
}

function esRelacion(x: unknown): x is BrechaRelacionada {
  const r = x as BrechaRelacionada;
  return Boolean(r) && Number.isInteger(r.respuestaId) && Number.isInteger(r.evaluacionId) && Number.isInteger(r.prioridad)
    && typeof r.descripcion === "string";
}

/** Lee el mapa guardado (borrador → brecha). Lo que no tenga la forma esperada se ignora. */
export function parsearRelaciones(texto: string | null): Record<number, BrechaRelacionada> {
  if (!texto) return {};
  try {
    const crudo = JSON.parse(texto) as Record<string, unknown>;
    const salida: Record<number, BrechaRelacionada> = {};
    for (const [k, v] of Object.entries(crudo ?? {})) {
      const id = Number(k);
      if (Number.isInteger(id) && id > 0 && esRelacion(v)) salida[id] = { ...v, descripcion: v.descripcion.slice(0, MAX_DESCRIPCION) };
    }
    return salida;
  } catch {
    return {};
  }
}

/** Agrega una relación conservando como máximo MAX_RELACIONES (se descartan las de id más bajo, las más antiguas). */
export function agregarRelacion(
  mapa: Record<number, BrechaRelacionada>,
  borradorId: number,
  relacion: BrechaRelacionada,
): Record<number, BrechaRelacionada> {
  const nuevo = { ...mapa, [borradorId]: relacion };
  const ids = Object.keys(nuevo).map(Number).sort((a, b) => b - a).slice(0, MAX_RELACIONES);
  return Object.fromEntries(ids.map((id) => [id, nuevo[id]]));
}

/** La brecha pendiente solo vale si es la que pide la URL (?brecha=ID). */
export function brechaPendienteValida(texto: string | null, brechaUrl: number | null): BrechaRelacionada | null {
  if (!texto || !brechaUrl) return null;
  try {
    const r = JSON.parse(texto) as unknown;
    return esRelacion(r) && r.respuestaId === brechaUrl ? r : null;
  } catch {
    return null;
  }
}

/** Enlace para volver a la brecha en el Plan de acción ("#3" busca por prioridad). */
export function hrefVolverABrecha(r: BrechaRelacionada): string {
  return `/panel/brechas?${new URLSearchParams({ evaluacion: String(r.evaluacionId), q: `#${r.prioridad}` }).toString()}`;
}

type AlmacenTexto = Pick<Storage, "getItem" | "setItem">;

function almacen(tipo: "local" | "session"): AlmacenTexto | null {
  try {
    if (typeof window === "undefined") return null;
    return tipo === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null; // modo privado / almacenamiento bloqueado
  }
}

export function recordarBrechaPendiente(r: BrechaRelacionada) {
  try {
    almacen("session")?.setItem(CLAVE_BRECHA_PENDIENTE, JSON.stringify(r));
  } catch {
    /* sin almacenamiento: el generador abre igual, solo sin el texto de la brecha */
  }
}

export function leerBrechaPendiente(brechaUrl: number | null): BrechaRelacionada | null {
  try {
    return brechaPendienteValida(almacen("session")?.getItem(CLAVE_BRECHA_PENDIENTE) ?? null, brechaUrl);
  } catch {
    return null;
  }
}

export function leerRelaciones(): Record<number, BrechaRelacionada> {
  try {
    return parsearRelaciones(almacen("local")?.getItem(CLAVE_RELACIONES) ?? null);
  } catch {
    return {};
  }
}

export function guardarRelacion(borradorId: number, r: BrechaRelacionada): Record<number, BrechaRelacionada> {
  const mapa = agregarRelacion(leerRelaciones(), borradorId, r);
  try {
    almacen("local")?.setItem(CLAVE_RELACIONES, JSON.stringify(mapa));
  } catch {
    /* sin almacenamiento */
  }
  return mapa;
}

/* ------------------------------------------------------------ historial */

/** El historial usa el vocabulario del cliente: "Borrador" (se puede editar) y "Final" (consolidado). */
export const ESTADO_HISTORIAL: Record<EstadoBorrador, { texto: string; tono: "medio" | "ok"; ayuda: string }> = {
  en_revision: { texto: "Borrador", tono: "medio", ayuda: "Puedes revisarlo y editarlo antes de dejarlo como final." },
  consolidado: { texto: "Final", tono: "ok", ayuda: "Quedó de solo lectura y su PDF está en Mis documentos." },
};

/** Formatos en que se descarga un documento generado (los que entrega el backend). */
export const FORMATOS_DOCUMENTO = ["PDF", "Markdown"] as const;

/* ------------------------------------------------------------ catálogo del generador */

export type IconoDocumento = "documento" | "escudo" | "diana" | "pdf" | "tabla" | "brechas" | "check";

/** Presentación de cada plantilla de borrador (los textos de fondo vienen del backend). */
export const PRESENTACION_PLANTILLA: Record<TipoBorrador, { icono: IconoDocumento; titulo: string; resumen: string; incluye: string[] }> = {
  politica_llm: {
    icono: "documento",
    titulo: "Política de uso de IA",
    resumen: "Reglas claras para que tu equipo use herramientas de IA de forma segura y responsable.",
    incluye: ["Roles y responsables", "Uso aceptable", "Datos personales", "Controles técnicos"],
  },
  aviso_privacidad: {
    icono: "escudo",
    titulo: "Aviso de privacidad",
    resumen: "Informa a tus clientes y usuarios cómo tratas sus datos y cómo ejercer sus derechos.",
    incluye: ["Finalidades", "Base de licitud", "Derechos del titular", "Transferencias"],
  },
  pia: {
    icono: "diana",
    titulo: "Evaluación de impacto (PIA)",
    resumen: "Analiza los riesgos de un tratamiento de datos de alto riesgo y las medidas para reducirlos.",
    incluye: ["Descripción del tratamiento", "Riesgos", "Medidas", "Conclusión"],
  },
};

/** Reportes que la plataforma ya genera en otras secciones (se abren desde aquí, sin duplicar lógica). */
export interface ReporteDisponible {
  id: "ejecutivo" | "brechas" | "rat" | "ropa" | "revision";
  icono: IconoDocumento;
  titulo: string;
  descripcion: string;
  incluye: string[];
  formatos: ("PDF" | "Excel" | "CSV" | "ZIP")[];
  ayuda: string;
  /** "descarga": se descarga aquí mismo; "enlace": se genera en su sección. */
  accion: "descarga" | "enlace";
  ruta?: string;
  /** Requiere una evaluación completada. */
  requiereEvaluacion?: boolean;
}

export const REPORTES: ReporteDisponible[] = [
  {
    id: "ejecutivo",
    icono: "pdf",
    titulo: "Reporte ejecutivo de cumplimiento",
    descripcion: "Resumen de tu madurez en gobernanza de IA, el nivel por dimensión y las brechas más urgentes.",
    incluye: ["Puntaje general", "Madurez por dimensión", "Brechas priorizadas", "Plan formativo"],
    formatos: ["PDF"],
    ayuda: "Se arma con tu evaluación completada más reciente. Es el mismo informe que puedes enviar por correo desde el Diagnóstico.",
    accion: "descarga",
    requiereEvaluacion: true,
  },
  {
    id: "brechas",
    icono: "brechas",
    titulo: "Informe de brechas",
    descripcion: "Listado de brechas con su severidad, impacto y la acción sugerida para cerrarlas.",
    incluye: ["Severidad", "Impacto", "Acción sugerida", "Filtros por normativa"],
    formatos: ["PDF", "CSV"],
    ayuda: "Se genera en el Plan de acción: filtra las brechas que necesites y descárgalas en PDF o CSV (se abre en Excel).",
    accion: "enlace",
    ruta: "/panel/brechas",
    requiereEvaluacion: true,
  },
  {
    id: "rat",
    icono: "tabla",
    titulo: "Registro de actividades de tratamiento",
    descripcion: "Informe de tu registro de actividades con la matriz de riesgos y un código para verificarlo.",
    incluye: ["Actividades", "Matriz de riesgos", "Código verificable"],
    formatos: ["PDF", "Excel"],
    ayuda: "Se genera desde tu registro de actividades. Necesita al menos una actividad registrada.",
    accion: "enlace",
    ruta: "/empresa/registro-actividades",
  },
  {
    id: "ropa",
    icono: "tabla",
    titulo: "Registro de actividades (RoPA)",
    descripcion: "El registro en el formato que piden las autoridades: como responsable y como encargado del tratamiento.",
    incluye: ["Como responsable", "Como encargado", "Transferencias"],
    formatos: ["PDF", "Excel"],
    ayuda: "Se genera desde tu registro de actividades, en la sección del informe RoPA.",
    accion: "enlace",
    ruta: "/empresa/registro-actividades",
  },
  {
    id: "revision",
    icono: "check",
    titulo: "Revisión interna del registro",
    descripcion: "Lista de verificación de tu registro y un paquete de evidencia verificable para auditorías.",
    incluye: ["Lista de verificación", "Diferencias entre versiones", "Paquete de evidencia"],
    formatos: ["PDF", "ZIP"],
    ayuda: "Se hace en la revisión interna de tu registro de actividades. El paquete de evidencia sirve para una auditoría interna.",
    accion: "enlace",
    ruta: "/empresa/registro-actividades/revision",
  },
];
