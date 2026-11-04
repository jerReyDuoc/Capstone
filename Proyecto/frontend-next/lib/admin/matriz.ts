/**
 * HU-24 · Mantenedor de la matriz normativa (panel interno de Therion Labs).
 *
 * Contratos de FastAPI /api/admin/matriz/* (app/api/routes/admin_matriz.py) y la lógica pura
 * que usa la página: campos de cada formulario, árbol de aplicabilidad y simulador del filtro
 * (espejo de app/domain/matriz/contenido.py, probado en tests/hu24_matriz.test.ts).
 *
 * Esta pantalla es interna: aquí sí se muestran los códigos (DAT-001, ERR-GOB-003, F1),
 * porque son el identificador con que el admin trabaja la matriz. El cliente nunca los ve.
 */
import { pedir } from "@/lib/encuesta/cliente";

export type Entidad = "controles" | "brechas" | "rutas" | "preguntas_filtro";
export type EstadoVersion = "borrador" | "publicada" | "reemplazada";
export type EstadoFila = "nuevo" | "modificado" | "retirado" | "restaurado" | "igual";

export interface Dominio { id: number; nombre_dominio: string | null }
export interface Ruta {
  id: number; nombre: string | null; dominio_id: number | null; nivel: string | null; objetivo: string | null;
  objetivos_especificos: string | null; contenidos: string | null; horas: number | null; modalidad: string | null;
  publico_objetivo: string | null; activo: boolean;
}
export interface Brecha {
  id: number; codigo_brecha: string | null; categoria: string | null; comportamiento_detectado: string | null;
  criticidad: string | null; accion_sistema: string | null; ruta_formativa_id: number | null; activo: boolean;
}
export interface Control {
  id: number; codigo_control: string | null; framework_fuente: string | null; articulo_referencia: string | null;
  tipo_fuente: string | null; obligacion: string | null; pregunta_evaluacion: string | null;
  aplicabilidad: string | null; evidencia_esperada: string | null; criticidad: string | null;
  recomendacion: string | null; test_asociado: string | null; dominio_id: number | null; brecha_id: number | null;
  aplica_siempre: boolean; filtros: number[]; activo: boolean;
}
export interface PreguntaFiltro {
  id: number; codigo: string; orden: number | null; pregunta: string | null; descripcion: string | null;
  activa: boolean; es_compuerta: boolean;
}
export interface Contenido {
  esquema: number; dominios: Dominio[]; rutas: Ruta[]; brechas: Brecha[]; controles: Control[];
  preguntas_filtro: PreguntaFiltro[];
}
export interface Arbol { compuertas: string[]; base: string[]; por_filtro: Record<string, string[]>; origen: string }

interface ItemDif { id: number; etiqueta: string; campos: string[] }
export type GrupoDif = { nuevos: ItemDif[]; modificados: ItemDif[]; retirados: ItemDif[]; restaurados: ItemDif[] };
export type Diferencias = { total: number } & Partial<Record<Entidad, GrupoDif>>;
export type Conteo = Partial<Record<Entidad, Partial<Record<keyof GrupoDif, number>>>>;

export interface Problema { nivel: "error" | "advertencia"; codigo: string; mensaje: string; entidad: string | null; id: number | null }

export interface FichaVersion {
  id: number; etiqueta: string | null; estado: EstadoVersion; version_texto: string | null; huella: string | null;
  nota_cambio: string | null; fecha_publicacion: string | null; fecha_creacion: string | null;
  publicado_por: { id: number; email: string | null } | null; evaluaciones: number;
  resumen: Record<Entidad, { activos: number; total: number }>;
}
export interface FichaBorrador {
  id: number; estado: "borrador"; revision: number; base_version_id: number | null; base_desactualizada: boolean;
  fecha_creacion: string | null; fecha_actualizacion: string | null; creado_por: { id: number; email: string | null } | null;
  cambios: number; conteo_cambios: Conteo; diferencias: Diferencias; errores: number; advertencias: number;
  resumen: Record<Entidad, { activos: number; total: number }>;
}
export interface EstadoMatriz { vigente: FichaVersion; borrador: FichaBorrador | null; etiqueta_sugerida: string }
export interface Borrador extends FichaBorrador { contenido: Contenido; arbol: Arbol }
export interface DetalleVersion extends FichaVersion {
  contenido: Contenido; arbol: Arbol; anterior: { id: number; etiqueta: string | null } | null;
  diferencias: Diferencias | null;
}
export interface Validacion {
  revision: number; problemas: Problema[]; errores: number; advertencias: number; diferencias: Diferencias;
  puede_publicar: boolean;
}
export interface ResultadoEdicion { revision: number; elemento: Record<string, unknown> | null; cambio: { operacion: string } }

const BASE = "/bff/admin/api/admin/matriz";
/** En la URL el guion bajo se escribe con guion. */
export const ruta = (e: Entidad) => (e === "preguntas_filtro" ? "preguntas-filtro" : e);

export const apiMatriz = {
  estado: () => pedir<EstadoMatriz>(BASE),
  versiones: () => pedir<{ items: FichaVersion[] }>(`${BASE}/versiones`),
  version: (id: number) => pedir<DetalleVersion>(`${BASE}/versiones/${id}`),
  borrador: () => pedir<Borrador>(`${BASE}/borrador`),
  crearBorrador: (desde?: number) =>
    pedir<Borrador>(`${BASE}/borrador`, { method: "POST", json: desde ? { desde_version_id: desde } : {} }),
  validacion: () => pedir<Validacion>(`${BASE}/borrador/validacion`),
  descartar: (revision: number) => pedir<{ descartado: boolean }>(`${BASE}/borrador/descartar`, { method: "POST", json: { revision } }),
  publicar: (revision: number, etiqueta: string, nota: string) =>
    pedir<FichaVersion & { diferencias: Diferencias }>(`${BASE}/borrador/publicar`, {
      method: "POST",
      json: { revision, etiqueta, nota_cambio: nota },
    }),
  crear: (e: Entidad, revision: number, datos: Record<string, unknown>) =>
    pedir<ResultadoEdicion>(`${BASE}/borrador/${ruta(e)}`, { method: "POST", json: { revision, datos } }),
  actualizar: (e: Entidad, id: number, revision: number, datos: Record<string, unknown>) =>
    pedir<ResultadoEdicion>(`${BASE}/borrador/${ruta(e)}/${id}`, { method: "PATCH", json: { revision, datos } }),
  retirar: (e: Entidad, id: number, revision: number) =>
    pedir<ResultadoEdicion>(`${BASE}/borrador/${ruta(e)}/${id}/retirar`, { method: "POST", json: { revision } }),
  restaurar: (e: Entidad, id: number, revision: number) =>
    pedir<ResultadoEdicion>(`${BASE}/borrador/${ruta(e)}/${id}/restaurar`, { method: "POST", json: { revision } }),
  aplicabilidad: (id: number, revision: number, aplica_siempre: boolean, filtros: number[]) =>
    pedir<ResultadoEdicion>(`${BASE}/borrador/controles/${id}/aplicabilidad`, {
      method: "PATCH",
      json: { revision, aplica_siempre, filtros },
    }),
};

// --------------------------------------------------------------------- formularios
export type TipoCampo = "texto" | "textoLargo" | "numero" | "si_no" | "criticidad" | "nivel" | "dominio" | "brecha" | "ruta";
export interface CampoForm {
  clave: string; etiqueta: string; tipo: TipoCampo; max?: number; requerido?: boolean; ayuda?: string;
  /** El código de un elemento ya publicado no se edita (identifica respuestas anteriores). */
  esCodigo?: boolean;
}

export const CRITICIDADES = ["Crítica", "Alta", "Media", "Baja"] as const;
export const NIVELES = ["Inicial", "Intermedio", "Avanzado"] as const;

export const CAMPOS: Record<Entidad, CampoForm[]> = {
  controles: [
    { clave: "codigo_control", etiqueta: "Código", tipo: "texto", max: 20, requerido: true, esCodigo: true, ayuda: "Ejemplo: GOB-011" },
    { clave: "pregunta_evaluacion", etiqueta: "Pregunta que ve el encuestado", tipo: "textoLargo", max: 500, requerido: true },
    { clave: "dominio_id", etiqueta: "Dimensión", tipo: "dominio", requerido: true },
    { clave: "criticidad", etiqueta: "Criticidad", tipo: "criticidad", requerido: true },
    { clave: "brecha_id", etiqueta: "Brecha si no se cumple", tipo: "brecha" },
    { clave: "obligacion", etiqueta: "Obligación", tipo: "texto", max: 200 },
    { clave: "framework_fuente", etiqueta: "Norma o marco", tipo: "texto", max: 50, ayuda: "Ejemplo: Ley N.º 21.719" },
    { clave: "articulo_referencia", etiqueta: "Artículo", tipo: "texto", max: 100 },
    { clave: "tipo_fuente", etiqueta: "Tipo de fuente", tipo: "texto", max: 50 },
    { clave: "aplicabilidad", etiqueta: "Aplicabilidad (texto descriptivo)", tipo: "texto", max: 100,
      ayuda: "Solo informativo. Lo que decide si se pregunta son las reglas del árbol." },
    { clave: "evidencia_esperada", etiqueta: "Evidencia esperada", tipo: "textoLargo", max: 5000 },
    { clave: "recomendacion", etiqueta: "Recomendación", tipo: "textoLargo", max: 5000 },
    { clave: "test_asociado", etiqueta: "Prueba asociada", tipo: "texto", max: 100 },
  ],
  brechas: [
    { clave: "codigo_brecha", etiqueta: "Código", tipo: "texto", max: 20, requerido: true, esCodigo: true, ayuda: "Ejemplo: ERR-GOB-012" },
    { clave: "comportamiento_detectado", etiqueta: "Comportamiento detectado", tipo: "textoLargo", max: 5000, requerido: true },
    { clave: "criticidad", etiqueta: "Criticidad", tipo: "criticidad", requerido: true },
    { clave: "categoria", etiqueta: "Categoría", tipo: "texto", max: 50 },
    { clave: "accion_sistema", etiqueta: "Acción del sistema", tipo: "texto", max: 100 },
    { clave: "ruta_formativa_id", etiqueta: "Ruta formativa que la cierra", tipo: "ruta" },
  ],
  rutas: [
    { clave: "nombre", etiqueta: "Nombre", tipo: "texto", max: 100, requerido: true },
    { clave: "dominio_id", etiqueta: "Dimensión", tipo: "dominio" },
    { clave: "nivel", etiqueta: "Nivel", tipo: "nivel" },
    { clave: "horas", etiqueta: "Horas", tipo: "numero" },
    { clave: "modalidad", etiqueta: "Modalidad", tipo: "texto", max: 50 },
    { clave: "publico_objetivo", etiqueta: "Público objetivo", tipo: "texto", max: 150 },
    { clave: "objetivo", etiqueta: "Objetivo general", tipo: "textoLargo", max: 5000 },
    { clave: "objetivos_especificos", etiqueta: "Objetivos específicos (uno por línea)", tipo: "textoLargo", max: 5000 },
    { clave: "contenidos", etiqueta: "Contenidos (uno por línea)", tipo: "textoLargo", max: 5000 },
  ],
  preguntas_filtro: [
    { clave: "codigo", etiqueta: "Código", tipo: "texto", max: 10, requerido: true, esCodigo: true, ayuda: "Ejemplo: F8" },
    { clave: "pregunta", etiqueta: "Pregunta del filtro", tipo: "textoLargo", max: 500, requerido: true },
    { clave: "descripcion", etiqueta: "Aclaración para el encuestado", tipo: "textoLargo", max: 500 },
    { clave: "orden", etiqueta: "Orden", tipo: "numero", requerido: true },
    { clave: "es_compuerta", etiqueta: "Es compuerta: si responden NO, no se aplica ninguna pregunta", tipo: "si_no" },
  ],
};

export const NOMBRE_ENTIDAD: Record<Entidad, { singular: string; plural: string }> = {
  controles: { singular: "control", plural: "Controles" },
  brechas: { singular: "brecha", plural: "Brechas" },
  rutas: { singular: "ruta formativa", plural: "Rutas formativas" },
  preguntas_filtro: { singular: "pregunta de filtro", plural: "Filtro inicial" },
};

const claveActivo = (e: Entidad) => (e === "preguntas_filtro" ? "activa" : "activo");

export function estaActivo(e: Entidad, item: object): boolean {
  return (item as Record<string, unknown>)[claveActivo(e)] !== false;
}

export function etiqueta(e: Entidad, item: object): string {
  const x = item as Record<string, unknown>;
  const v = e === "controles" ? x.codigo_control : e === "brechas" ? x.codigo_brecha : e === "rutas" ? x.nombre : x.codigo;
  return typeof v === "string" && v ? v : `#${x.id}`;
}

/** Texto principal de la fila (lo que el admin lee para reconocer el elemento). */
export function descripcion(e: Entidad, item: object): string {
  const x = item as Record<string, unknown>;
  const v = e === "controles" ? x.pregunta_evaluacion : e === "brechas" ? x.comportamiento_detectado
    : e === "rutas" ? x.objetivo : x.pregunta;
  return typeof v === "string" ? v : "";
}

/** Valores iniciales del formulario (para crear o editar). */
export function valoresIniciales(e: Entidad, item?: object | null): Record<string, string | boolean> {
  const x = (item ?? {}) as Record<string, unknown>;
  const salida: Record<string, string | boolean> = {};
  for (const c of CAMPOS[e]) {
    const v = x[c.clave];
    salida[c.clave] = c.tipo === "si_no" ? v === true : v === null || v === undefined ? "" : String(v);
  }
  return salida;
}

/**
 * Del formulario al cuerpo de la API. Al editar solo se envía lo que cambió (el backend
 * responde SIN_CAMBIOS si no hay nada) y el código de un elemento publicado nunca se envía.
 */
export function datosDelFormulario(
  e: Entidad,
  valores: Record<string, string | boolean>,
  original?: object | null,
): Record<string, unknown> {
  const orig = (original ?? null) as Record<string, unknown> | null;
  const publicado = orig !== null && typeof orig.id === "number" && orig.id > 0;
  const datos: Record<string, unknown> = {};
  for (const c of CAMPOS[e]) {
    if (c.esCodigo && publicado) continue;
    const crudo = valores[c.clave];
    let v: unknown;
    if (c.tipo === "si_no") v = crudo === true;
    else if (["numero", "dominio", "brecha", "ruta"].includes(c.tipo)) {
      const t = String(crudo ?? "").trim();
      v = t === "" ? null : Number(t);
    } else {
      const t = String(crudo ?? "").trim();
      v = t === "" ? null : t;
    }
    if (orig) {
      const antes = orig[c.clave] ?? (c.tipo === "si_no" ? false : null);
      if (antes === v) continue;
    } else if (v === null || v === false) {
      continue;
    }
    datos[c.clave] = v;
  }
  return datos;
}

/** Errores del formulario antes de enviar (los definitivos los da el backend). */
export function erroresFormulario(e: Entidad, valores: Record<string, string | boolean>, esNuevo: boolean): Record<string, string> {
  const errores: Record<string, string> = {};
  for (const c of CAMPOS[e]) {
    if (c.esCodigo && !esNuevo) continue;
    const v = valores[c.clave];
    const t = typeof v === "string" ? v.trim() : "";
    if (c.requerido && c.tipo !== "si_no" && t === "") errores[c.clave] = "Completa este campo.";
    else if (c.max && t.length > c.max) errores[c.clave] = `Máximo ${c.max} caracteres (llevas ${t.length}).`;
    else if (c.tipo === "numero" && t !== "" && !/^\d{1,6}$/.test(t)) errores[c.clave] = "Usa un número entero positivo.";
  }
  return errores;
}

// --------------------------------------------------------------------- diferencias
export function estadosDe(dif: Diferencias | null | undefined, e: Entidad): Map<number, EstadoFila> {
  const m = new Map<number, EstadoFila>();
  const g = dif?.[e];
  if (!g) return m;
  g.nuevos.forEach((x) => m.set(x.id, "nuevo"));
  g.modificados.forEach((x) => m.set(x.id, "modificado"));
  g.retirados.forEach((x) => m.set(x.id, "retirado"));
  g.restaurados.forEach((x) => m.set(x.id, "restaurado"));
  return m;
}

export const ETIQUETA_ESTADO_FILA: Record<EstadoFila, { texto: string; tono: string }> = {
  nuevo: { texto: "Nuevo", tono: "ok" },
  modificado: { texto: "Modificado", tono: "medio" },
  retirado: { texto: "Retirado", tono: "alto" },
  restaurado: { texto: "Restaurado", tono: "info" },
  igual: { texto: "Sin cambios", tono: "info" },
};

/** "3 controles nuevos, 1 brecha modificada…" para el resumen del borrador. */
export function frasesCambios(conteo: Conteo): string[] {
  const frases: string[] = [];
  const nombres: Record<Entidad, [string, string]> = {
    controles: ["control", "controles"], brechas: ["brecha", "brechas"],
    rutas: ["ruta", "rutas"], preguntas_filtro: ["pregunta de filtro", "preguntas de filtro"],
  };
  const fem = (e: Entidad) => e !== "controles";
  const verbos: Record<keyof GrupoDif, [string, string]> = {
    nuevos: ["nuevo", "nueva"], modificados: ["modificado", "modificada"],
    retirados: ["retirado", "retirada"], restaurados: ["restaurado", "restaurada"],
  };
  for (const e of ["controles", "brechas", "rutas", "preguntas_filtro"] as Entidad[]) {
    const g = conteo[e];
    if (!g) continue;
    for (const k of ["nuevos", "modificados", "retirados", "restaurados"] as (keyof GrupoDif)[]) {
      const n = g[k];
      if (!n) continue;
      const verbo = verbos[k][fem(e) ? 1 : 0] + (n > 1 ? "s" : "");
      frases.push(`${n} ${n > 1 ? nombres[e][1] : nombres[e][0]} ${verbo}`);
    }
  }
  return frases;
}

// --------------------------------------------------------------------- árbol y simulador
/** Espejo de ArbolAplicabilidad.aplicables (app/domain/matriz/contenido.py). */
export function aplicables(contenido: Contenido, respuestas: Record<string, boolean>): string[] {
  const preguntas = new Map(contenido.preguntas_filtro.filter((p) => p.activa).map((p) => [p.id, p]));
  const compuertas = [...preguntas.values()].filter((p) => p.es_compuerta).map((p) => p.codigo);
  if (compuertas.some((c) => !respuestas[c])) return [];
  const salida = new Set<string>();
  for (const c of contenido.controles) {
    if (!c.activo || !c.codigo_control) continue;
    if (c.aplica_siempre) salida.add(c.codigo_control);
    for (const f of c.filtros) {
      const p = preguntas.get(f);
      if (p && respuestas[p.codigo]) salida.add(c.codigo_control);
    }
  }
  return [...salida].sort();
}

export function filtrosOrdenados(contenido: Contenido, incluirRetiradas = false): PreguntaFiltro[] {
  return [...contenido.preguntas_filtro]
    .filter((p) => incluirRetiradas || p.activa)
    .sort((a, b) => (a.orden ?? 0) - (b.orden ?? 0) || a.id - b.id);
}

/** Controles activos agrupados por dimensión, en orden de código. */
export function controlesPorDimension(contenido: Contenido): { dominio: Dominio; controles: Control[] }[] {
  return contenido.dominios
    .map((d) => ({
      dominio: d,
      controles: contenido.controles
        .filter((c) => c.activo && c.dominio_id === d.id)
        .sort((a, b) => (a.codigo_control ?? "").localeCompare(b.codigo_control ?? "")),
    }))
    .filter((g) => g.controles.length > 0);
}

export function fechaCorta(iso?: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("es-CL", { day: "numeric", month: "short", year: "numeric" }) : "—";
}

export function huellaCorta(h?: string | null): string {
  return h ? h.slice(0, 8).toUpperCase() : "—";
}

export function mensajeErrorMatriz(codigo: string): string | null {
  switch (codigo) {
    case "BORRADOR_CAMBIADO":
      return "Otro administrador cambió el borrador mientras editabas. Recargamos la última versión; revisa y vuelve a intentar.";
    case "SIN_BORRADOR":
      return "El borrador ya no existe (alguien lo publicó o lo descartó). Recargamos el estado.";
    default:
      return null;
  }
}
