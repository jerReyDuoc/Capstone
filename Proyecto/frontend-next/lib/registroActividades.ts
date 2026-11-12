/**
 * Registro de actividades de tratamiento (navegador → /bff/cliente/api/registro-actividades).
 *
 * El backend guarda cada actividad, calcula lo que toma del mapa de datos, su completitud y las
 * transiciones de estado, y guarda una versión inmutable cada vez que una actividad queda vigente.
 * Aquí van las llamadas y la lógica pura de presentación (probada en tests/registro_actividades.test.ts):
 *   - la vista previa de lo que la actividad toma del mapa mientras el usuario elige (sin esperar al
 *     servidor; el servidor sigue siendo la fuente de la completitud oficial);
 *   - qué cambió en el formulario (solo se envía eso) y en qué paso está cada campo;
 *   - filtros y búsqueda de la lista.
 */
import { pedir } from "@/lib/encuesta/cliente";
import type { CatalogoMapa, ElementoMapa, FlujoMapa, VistaMapa } from "@/lib/mapaDatos";

export const BASE_RAT = "/bff/cliente/api/registro-actividades";

/* ============================================================ tipos */

export type EstadoActividad = "borrador" | "en_revision" | "vigente" | "archivada";
export type AccionEstado = "enviar_revision" | "volver_borrador" | "aprobar" | "nueva_version" | "archivar" | "reactivar";
export type CodigoCampo =
  | "tipos_datos" | "ambito" | "bases_datos" | "titulares" | "finalidades" | "fuentes" | "base_licitud"
  | "destinatarios" | "transferencias" | "conservacion" | "decisiones" | "medidas" | "rol";

export interface OpcionRat {
  codigo: string;
  nombre: string;
  descripcion?: string;
  referencia?: string;
  grupo?: string;
  acceso_publico?: boolean;
}

export interface CatalogoRat {
  version_textos: string;
  revision_legal: { estado: string; fecha: string | null };
  aviso: string;
  estados: OpcionRat[];
  bases_licitud: OpcionRat[];
  bases_sensibles: OpcionRat[];
  fuentes: OpcionRat[];
  unidades_plazo: OpcionRat[];
  inicios_plazo: OpcionRat[];
  max_plazo: Record<string, number>;
  grupos_medidas: string[];
  medidas_seguridad: OpcionRat[];
  roles_empresa: OpcionRat[];
  campos: { codigo: CodigoCampo; titulo: string; paso: number; ayuda: string; desde_mapa: boolean }[];
  pasos: { numero: number; titulo: string; descripcion: string }[];
}

export interface Seleccion {
  id: number;
  categorias_datos: string[];
  categorias_titulares: string[];
}

export interface Fuente {
  tipo: string;
  detalle: string | null;
}

export interface Plazo {
  categoria: string;
  plazo: number | null;
  unidad: string | null;
  desde: string | null;
  fundamento: string | null;
}

export interface Decisiones {
  existe: boolean | null;
  perfilamiento: boolean;
  logica: string | null;
  consecuencias: string | null;
  intervencion_humana: boolean | null;
}

export interface ContenidoActividad {
  nombre: string;
  descripcion: string | null;
  area: string | null;
  elementos: Seleccion[];
  flujos: Seleccion[];
  finalidades: string[];
  fuentes: Fuente[];
  base_licitud: string | null;
  interes_legitimo: string | null;
  base_sensibles: string | null;
  sin_destinatarios: boolean;
  plazos: Plazo[];
  decisiones: Decisiones;
  medidas: { codigos: string[]; otras: string | null };
  rol: string | null;
  responsable_mandante: string | null;
  ambito_nota: string | null;
}

export interface EstadoCampo {
  completo: boolean;
  faltante: string | null;
  aplica: boolean;
  titulo: string;
  paso: number;
}

export interface Faltante {
  codigo: CodigoCampo;
  titulo: string;
  paso: number;
  mensaje: string;
}

export interface Completitud {
  porcentaje: number;
  completos: number;
  total: number;
  faltantes: Faltante[];
  puede_quedar_vigente: boolean;
  campos?: Record<CodigoCampo, EstadoCampo>;
  advertencias?: string[];
}

export interface Derivados {
  elementos: {
    id: number; tipo: string; nombre: string; pais: string | null; categorias_datos: string[];
    categorias_titulares: string[]; sensibles: string[]; rol_tercero: string | null;
  }[];
  flujos: {
    id: number; nombre: string; categorias_datos: string[]; categorias_titulares: string[]; internacional: boolean;
    pais_origen: string | null; pais_destino: string | null; garantia: string | null; garantia_valida: boolean;
  }[];
  no_encontrados: { tipo: "elemento" | "flujo"; id: number }[];
  tipos_datos: { codigo: string; nombre: string; sensible: boolean }[];
  hay_sensibles: boolean;
  titulares: { codigo: string; nombre: string; nna: boolean }[];
  incluye_nna: boolean;
  bases_datos: { id: number; nombre: string; tipo: string }[];
  paises: { codigo: string; nombre: string }[];
  terceros: { id: number; nombre: string; pais: string | null; rol_tercero: string | null; contrato_firmado: boolean | null }[];
  transferencias: {
    flujo_id: number; nombre: string; pais_destino: string | null; pais_nombre: string; garantia: string | null;
    garantia_nombre: string; garantia_valida: boolean;
  }[];
  fuera_de_chile_sin_flujo: { id: number; nombre: string; pais: string; pais_nombre: string }[];
}

export interface MotivoRevision {
  fecha: string;
  texto: string;
  version_mapa: number;
}

export interface ResumenActividad {
  tipos_datos: number;
  hay_sensibles: boolean;
  incluye_nna: boolean;
  sistemas: number;
  terceros: number;
  transferencias: number;
  paises: string[];
  base_licitud: string | null;
  rol: string | null;
  finalidades: number;
}

export interface Actividad {
  id: number;
  nombre: string;
  estado: EstadoActividad;
  estado_nombre: string;
  estado_previo: EstadoActividad | null;
  revision: number;
  version_vigente: number | null;
  editable: boolean;
  acciones: AccionEstado[];
  completitud: Completitud;
  motivos_revision: MotivoRevision[];
  resumen: ResumenActividad;
  area: string | null;
  fecha_creacion: string | null;
  fecha_actualizacion: string | null;
  fecha_vigencia: string | null;
  fecha_archivo: string | null;
  /** Solo en el detalle */
  contenido?: ContenidoActividad;
  derivados?: Derivados;
}

export interface ListaRegistro {
  actividades: Actividad[];
  global: {
    porcentaje: number;
    actividades: number;
    completas: number;
    por_estado: Record<EstadoActividad, number>;
    por_revisar: number;
  };
  mapa: { version: number; elementos: number; flujos: number; iniciado: boolean };
  limites: { max_actividades: number };
}

export interface RespuestaActividad {
  actividad: Actividad;
  cambio?: string | null;
  mensaje?: string;
  version_creada?: number | null;
}

export interface VersionResumen {
  numero: number;
  fecha: string | null;
  huella: string;
  resumen: string;
  cambios: { codigo: string; titulo: string }[];
  version_mapa: number;
}

export interface InstantaneaVersion {
  numero: number;
  fecha: string | null;
  huella: string;
  resumen: string;
  version_mapa: number;
  es_la_vigente: boolean;
  verificada: boolean;
  contenido: { actividad: ContenidoActividad; mapa: Pick<Derivados, "elementos" | "flujos" | "tipos_datos" | "titulares" | "bases_datos" | "paises" | "terceros" | "transferencias"> };
}

/* ============================================================ llamadas */

export const cargarCatalogoRat = () => pedir<CatalogoRat>(`${BASE_RAT}/catalogo`);
export const cargarRegistro = () => pedir<ListaRegistro>(BASE_RAT);
export const cargarActividad = (id: number) =>
  pedir<{ actividad: Actividad; mapa: { version: number } }>(`${BASE_RAT}/actividades/${id}`);
export const crearActividad = (datos: Partial<ContenidoActividad> & { nombre: string }) =>
  pedir<RespuestaActividad>(`${BASE_RAT}/actividades`, { method: "POST", json: datos });
export const editarActividad = (id: number, revision: number, datos: Partial<ContenidoActividad>) =>
  pedir<RespuestaActividad>(`${BASE_RAT}/actividades/${id}`, { method: "PATCH", json: { revision, ...datos } });
export const cambiarEstado = (id: number, revision: number, accion: AccionEstado) =>
  pedir<RespuestaActividad>(`${BASE_RAT}/actividades/${id}/estado`, { method: "POST", json: { revision, accion } });
export const cargarVersionesActividad = (id: number) =>
  pedir<{ version_vigente: number | null; estado: EstadoActividad; versiones: VersionResumen[] }>(`${BASE_RAT}/actividades/${id}/versiones`);
export const cargarVersionActividad = (id: number, numero: number) =>
  pedir<InstantaneaVersion>(`${BASE_RAT}/actividades/${id}/versiones/${numero}`);

/* ============================================================ textos */

export const ETIQUETA_ESTADO: Record<EstadoActividad, string> = {
  borrador: "Borrador",
  en_revision: "En revisión",
  vigente: "Vigente",
  archivada: "Archivada",
};

/** Clase de color de la insignia de cada estado (globals.css). */
export const TONO_ESTADO: Record<EstadoActividad, string> = {
  borrador: "tone-info",
  en_revision: "tone-medio",
  vigente: "tone-ok",
  archivada: "tone-bajo",
};

export const ETIQUETA_ACCION_ESTADO: Record<AccionEstado, string> = {
  enviar_revision: "Enviar a revisión",
  volver_borrador: "Volver a borrador",
  aprobar: "Dejar vigente",
  nueva_version: "Editar en una nueva versión",
  archivar: "Archivar",
  reactivar: "Reactivar",
};

/* ============================================================ contenido y cambios */

export function contenidoVacio(nombre = ""): ContenidoActividad {
  return {
    nombre, descripcion: null, area: null, elementos: [], flujos: [], finalidades: [], fuentes: [], base_licitud: null,
    interes_legitimo: null, base_sensibles: null, sin_destinatarios: false, plazos: [],
    decisiones: { existe: null, perfilamiento: false, logica: null, consecuencias: null, intervencion_humana: null },
    medidas: { codigos: [], otras: null }, rol: null, responsable_mandante: null, ambito_nota: null,
  };
}

const CLAVES: (keyof ContenidoActividad)[] = [
  "nombre", "descripcion", "area", "elementos", "flujos", "finalidades", "fuentes", "base_licitud", "interes_legitimo",
  "base_sensibles", "sin_destinatarios", "plazos", "decisiones", "medidas", "rol", "responsable_mandante", "ambito_nota",
];

/** Texto vacío o con solo espacios = sin valor (como lo guarda el servidor). */
export function limpiarTexto(v: string | null | undefined): string | null {
  const t = (v ?? "").trim();
  return t ? t : null;
}

/** Forma comparable de un valor: textos sin espacios en los extremos y "" igual a sin valor. */
function canonico(v: unknown): string {
  return JSON.stringify(v ?? null, (_k, x) => (typeof x === "string" ? (x.trim() || null) : x));
}

/** Lo que cambió entre lo guardado y el borrador del formulario (solo eso se envía al guardar). */
export function cambiosContenido(guardado: ContenidoActividad, borrador: ContenidoActividad): Partial<ContenidoActividad> {
  const salida: Partial<ContenidoActividad> = {};
  for (const k of CLAVES) {
    if (canonico(guardado[k]) !== canonico(borrador[k])) {
      (salida as Record<string, unknown>)[k] = borrador[k];
    }
  }
  return salida;
}

/** El campo del registro y el paso del formulario en que se completa cada parte del contenido. */
export const PASO_DE_CLAVE: Record<keyof ContenidoActividad, number> = {
  nombre: 1, descripcion: 1, area: 1, finalidades: 1, rol: 1, responsable_mandante: 1,
  elementos: 2, flujos: 2, ambito_nota: 2,
  fuentes: 3, base_licitud: 3, interes_legitimo: 3, base_sensibles: 3,
  sin_destinatarios: 4,
  plazos: 5, decisiones: 5,
  medidas: 6,
};

/** Campos pendientes agrupados por paso: {paso: n} (para marcar los pasos del formulario). */
export function pendientesPorPaso(c: Completitud): Record<number, number> {
  const salida: Record<number, number> = {};
  for (const f of c.faltantes) salida[f.paso] = (salida[f.paso] ?? 0) + 1;
  return salida;
}

/* ============================================================ vista previa desde el mapa */

/**
 * Lo que la actividad toma del mapa con lo que el usuario está eligiendo (mismo cálculo que el
 * servidor, con los datos que ya trae el mapa: país efectivo, transferencias y garantías).
 */
export function vistaPreviaDesdeMapa(
  elegidos: { elementos: Seleccion[]; flujos: Seleccion[] },
  mapa: Pick<VistaMapa, "elementos" | "flujos">,
  catalogo: CatalogoMapa | null,
) {
  const porId = new Map<number, ElementoMapa>(mapa.elementos.map((e) => [e.id, e]));
  const flujoPorId = new Map<number, FlujoMapa>(mapa.flujos.map((f) => [f.id, f]));
  const datos = new Set<string>();
  const titulares = new Set<string>();
  const paises = new Set<string>();
  const terceros = new Map<number, string>();
  const bases: string[] = [];
  const transferencias: { flujo: number; nombre: string; pais: string | null; garantiaValida: boolean }[] = [];
  const noEncontrados: number[] = [];

  const efectivas = (elegidas: string[], disponibles: string[]) => elegidas.filter((c) => disponibles.includes(c));

  for (const s of elegidos.elementos) {
    const e = porId.get(s.id);
    if (!e) {
      noEncontrados.push(s.id);
      continue;
    }
    efectivas(s.categorias_datos, e.categorias_datos).forEach((c) => datos.add(c));
    efectivas(s.categorias_titulares, e.categorias_titulares).forEach((c) => titulares.add(c));
    if (e.derivados.pais_efectivo) paises.add(e.derivados.pais_efectivo);
    if (e.tipo === "tercero") terceros.set(e.id, e.nombre);
    else bases.push(e.nombre);
  }
  for (const s of elegidos.flujos) {
    const f = flujoPorId.get(s.id);
    if (!f) {
      noEncontrados.push(s.id);
      continue;
    }
    efectivas(s.categorias_datos, f.categorias_datos).forEach((c) => datos.add(c));
    efectivas(s.categorias_titulares, f.categorias_titulares).forEach((c) => titulares.add(c));
    for (const p of [f.derivados.pais_origen, f.derivados.pais_destino]) if (p) paises.add(p);
    const destino = porId.get(f.destino_id);
    if (destino?.tipo === "tercero") terceros.set(destino.id, destino.nombre);
    if (f.derivados.internacional) {
      transferencias.push({
        flujo: f.id, nombre: nombreFlujo(f, porId), pais: f.derivados.pais_destino, garantiaValida: f.derivados.garantia_valida,
      });
    }
  }
  const sensibles = new Set(catalogo?.categorias_datos.filter((c) => c.sensible).map((c) => c.codigo) ?? []);
  const ordenDatos = new Map(catalogo?.categorias_datos.map((c, i) => [c.codigo, i]) ?? []);
  const tipos = [...datos].sort(
    (a, b) => Number(sensibles.has(b)) - Number(sensibles.has(a)) || (ordenDatos.get(a) ?? 999) - (ordenDatos.get(b) ?? 999),
  );
  const nna = new Set(catalogo?.categorias_titulares.filter((t) => t.nna).map((t) => t.codigo) ?? []);
  return {
    tiposDatos: tipos,
    haySensibles: tipos.some((c) => sensibles.has(c)),
    titulares: [...titulares],
    incluyeNna: [...titulares].some((t) => nna.has(t)),
    paises: [...paises].sort((a, b) => Number(a !== "CL") - Number(b !== "CL") || a.localeCompare(b)),
    terceros: [...terceros.values()].sort((a, b) => a.localeCompare(b, "es")),
    bases,
    transferencias,
    noEncontrados,
  };
}

export function nombreFlujo(f: FlujoMapa, porId: Map<number, ElementoMapa>): string {
  return `${porId.get(f.origen_id)?.nombre ?? "?"} → ${porId.get(f.destino_id)?.nombre ?? "?"}`;
}

/** Al elegir un elemento o flujo del mapa se proponen todas sus categorías (el usuario puede quitar). */
export function seleccionInicial(x: { id: number; categorias_datos: string[]; categorias_titulares: string[] }): Seleccion {
  return { id: x.id, categorias_datos: [...x.categorias_datos], categorias_titulares: [...x.categorias_titulares] };
}

/** Los plazos de conservación quedan alineados con los tipos de datos actuales (uno por categoría). */
export function alinearPlazos(plazos: Plazo[], categorias: string[]): Plazo[] {
  const porCategoria = new Map(plazos.map((p) => [p.categoria, p]));
  return categorias.map((c) => porCategoria.get(c) ?? { categoria: c, plazo: null, unidad: null, desde: null, fundamento: null });
}

/** Copia el plazo de una fila al resto de las categorías. */
export function aplicarPlazoATodas(plazos: Plazo[], desde: Plazo): Plazo[] {
  return plazos.map((p) => ({ ...p, plazo: desde.plazo, unidad: desde.unidad, desde: desde.desde, fundamento: desde.fundamento }));
}

/* ============================================================ lista */

export type FiltroEstado = "activas" | EstadoActividad;

export function filtrarActividades(lista: Actividad[], filtro: FiltroEstado, busqueda: string): Actividad[] {
  const q = busqueda.trim().toLocaleLowerCase("es");
  return lista
    .filter((a) => (filtro === "activas" ? a.estado !== "archivada" : a.estado === filtro))
    .filter((a) => !q || a.nombre.toLocaleLowerCase("es").includes(q) || (a.area ?? "").toLocaleLowerCase("es").includes(q))
    .sort((a, b) => Number(b.estado === "en_revision" && b.motivos_revision.length > 0)
      - Number(a.estado === "en_revision" && a.motivos_revision.length > 0) || a.nombre.localeCompare(b.nombre, "es"));
}

/** Frase corta del estado de la versión, para la lista y el detalle. */
export function textoVersion(a: Pick<Actividad, "estado" | "version_vigente">): string {
  if (a.version_vigente === null) return a.estado === "archivada" ? "Nunca estuvo vigente" : "Aún sin versión vigente";
  if (a.estado === "vigente") return `Versión ${a.version_vigente} vigente`;
  if (a.estado === "archivada") return `Última versión vigente: ${a.version_vigente}`;
  return `Sigue valiendo la versión ${a.version_vigente} mientras completas los cambios`;
}
