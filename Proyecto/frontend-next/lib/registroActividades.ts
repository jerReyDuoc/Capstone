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
  /** Cuántas personas abarca la actividad (dato opcional que usa el nivel de riesgo). */
  volumenes?: OpcionRat[];
  ayuda_volumen?: string;
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
  /** Opcional: a cuántas personas alcanza la actividad (solo existe si tiene valor). */
  volumen?: string | null;
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
  /** Sistemas, bases o proveedores con inteligencia artificial que usa la actividad. */
  sistemas_ia?: { id: number; nombre: string; subtipo_nombre: string }[];
}

/* ============================================================ nivel de riesgo de la actividad */

export type NivelRiesgo = "Bajo" | "Medio" | "Alto" | "Crítico";

export interface FactorRiesgo {
  eje: "probabilidad" | "impacto";
  puntos: number;
  titulo: string;
  detalle: string;
  tratamiento: string;
}

export interface RiesgoActividad {
  nivel: NivelRiesgo;
  puntaje: number;
  probabilidad: number;
  impacto: number;
  /** Se recomienda una evaluación de impacto y por qué. */
  requiere_pia: boolean;
  motivos_pia: string[];
  /** Parte de la matriz de las actividades de mayor riesgo. */
  mayor_riesgo: boolean;
  /** Solo en el detalle */
  factores?: FactorRiesgo[];
  tratamientos?: string[];
  probabilidad_nombre?: string;
  impacto_nombre?: string;
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
  /** Nivel de riesgo con reglas explicables (null si todavía no elige nada del mapa). */
  riesgo?: RiesgoActividad | null;
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
  riesgos?: {
    por_nivel: Record<NivelRiesgo, number>;
    mayor_riesgo: number;
    pia_recomendadas: number;
    metodologia: string;
    metodologia_pia: string;
    referencia: string;
  };
}

export interface RespuestaActividad {
  actividad: Actividad;
  cambio?: string | null;
  mensaje?: string;
  version_creada?: number | null;
  /** Al dejarla vigente: si el registro ya cuenta como evidencia en la evaluación. */
  evidencia?: ResultadoEvidencia | null;
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
  "volumen",
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
  elementos: 2, flujos: 2, ambito_nota: 2, volumen: 2,
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

/* ============================================================ riesgo, evidencia y brechas del registro */

/** Clase de color de la insignia de cada nivel de riesgo (globals.css). */
export const TONO_RIESGO: Record<NivelRiesgo, string> = {
  Bajo: "tone-ok",
  Medio: "tone-medio",
  Alto: "tone-alto",
  Crítico: "tone-critico",
};

/** Texto corto del riesgo para la lista ("Riesgo alto · evaluación de impacto recomendada"). */
export function textoRiesgo(r: RiesgoActividad | null | undefined): string {
  if (!r) return "Riesgo sin calcular: elige del mapa los sistemas de la actividad";
  return `Riesgo ${r.nivel.toLocaleLowerCase("es")}${r.requiere_pia ? " · evaluación de impacto recomendada" : ""}`;
}

export interface ControlRespaldado {
  respuesta_id: number;
  obligacion: string | null;
  estado_actual: string | null;
  estado_actual_nombre: string | null;
  estado_aportado: string | null;
  estado_aportado_nombre: string | null;
  motivo: string | null;
  mejora: boolean;
  respaldado_por_registro: boolean;
}

export interface ResultadoEvidencia {
  aplicado: boolean;
  motivo: "sin_evaluacion" | "registro_incompleto" | "sin_mejoras" | null;
  mensaje: string;
  evaluacion_id?: number;
  faltantes?: string[];
  controles: {
    respuesta_id: number; evidencia_id: number; estado_previo: string | null; estado_resultante: string;
    obligacion: string | null; puntaje_previo: number | null; puntaje_resultante: number | null;
  }[];
  puntaje_previo?: number | null;
  puntaje_resultante?: number | null;
}

export type CodigoBrechaRegistro = "sin_base_licitud" | "sin_plazo" | "transferencia_sin_garantia" | "flujo_sin_actividad";

export interface BrechaRegistro {
  codigo: CodigoBrechaRegistro;
  titulo: string;
  texto: string;
  severidad: "Crítica" | "Alta" | "Media" | "Baja";
  paso: number | null;
  actividad: { id: number; nombre: string } | null;
  flujo_id: number | null;
  obligacion: string | null;
  ruta: { id: number; nombre: string | null; nivel: string | null; horas: number | null;
          estado: "no_iniciado" | "en_curso" | "completado" } | null;
  remediacion: { evaluacion_id: number; respuesta_id: number; estado: string | null; estado_nombre: string | null;
                 abierta: boolean } | null;
}

export interface ActividadMayorRiesgo {
  actividad_id: number;
  nombre: string;
  estado: EstadoActividad;
  estado_nombre: string;
  version: number | null;
  origen: "vigente" | "trabajo";
  nivel: NivelRiesgo;
  puntaje: number;
  probabilidad: number;
  impacto: number;
  requiere_pia: boolean;
  motivos_pia: string[];
  factores: string[];
  tratamientos: string[];
}

export interface CumplimientoRegistro {
  mapa: { iniciado: boolean; version: number; elementos: number; flujos: number; flujos_sin_actividad: number };
  registro: {
    activas: number; vigentes: number; completas: number; en_revision: number; borradores: number;
    por_revisar: number; completitud: number; vigente_completo: boolean; faltantes: string[];
  };
  riesgos: {
    referencia: string; metodologia: string; metodologia_pia: string; por_nivel: Record<NivelRiesgo, number>;
    mayor_riesgo: ActividadMayorRiesgo[]; pia_recomendadas: number; mapa_calor: number[][];
  };
  brechas: BrechaRegistro[];
  evidencia: {
    evaluacion_id: number | null; aplicable: boolean; faltantes: string[]; controles: ControlRespaldado[];
    por_mejorar: number; puntaje_general: number | null;
  };
  borradores: { pia: { recomendada: boolean; actividades: number }; aviso: { finalidades: number } };
}

export const cargarCumplimiento = () => pedir<CumplimientoRegistro>(`${BASE_RAT}/cumplimiento`);
export const usarRegistroComoEvidencia = () =>
  pedir<ResultadoEvidencia>(`${BASE_RAT}/cumplimiento/evidencia`, { method: "POST", json: {} });

/** Dónde se corrige cada brecha: la actividad en su paso, o el mapa de datos (envíos y garantías). */
export function hrefCorregirBrecha(b: Pick<BrechaRegistro, "codigo" | "actividad" | "paso">): { href: string; texto: string } {
  if (b.codigo === "transferencia_sin_garantia") {
    return { href: "/empresa/mapa-datos", texto: "Registrar la garantía en el mapa" };
  }
  if (b.codigo === "flujo_sin_actividad" || !b.actividad) {
    return { href: "/empresa/registro-actividades", texto: "Registrar la actividad" };
  }
  const paso = b.paso ? `&paso=${b.paso}` : "";
  return { href: `/empresa/registro-actividades?actividad=${b.actividad.id}${paso}`, texto: "Corregir la actividad" };
}

/** Pasos de la ruta de remediación de una brecha, en orden (corregir, formarse, re-evaluar). */
export function rutaRemediacion(b: BrechaRegistro): { clave: string; texto: string; href: string; hecho?: boolean }[] {
  const pasos: { clave: string; texto: string; href: string; hecho?: boolean }[] = [];
  const corregir = hrefCorregirBrecha(b);
  pasos.push({ clave: "corregir", texto: corregir.texto, href: corregir.href });
  if (b.ruta) {
    const estado = b.ruta.estado === "completado" ? "completado" : b.ruta.estado === "en_curso" ? "en curso" : "sin empezar";
    pasos.push({
      clave: "formacion", texto: `Módulo «${b.ruta.nombre ?? "de formación"}» (${estado})`,
      href: `/panel/capacitacion/${b.ruta.id}${b.remediacion ? `?evaluacion=${b.remediacion.evaluacion_id}` : ""}`,
      hecho: b.ruta.estado === "completado",
    });
  }
  if (b.remediacion?.abierta) {
    pasos.push({
      clave: "remediacion", texto: `Re-evaluar el control (hoy: ${(b.remediacion.estado_nombre ?? "con brecha").toLocaleLowerCase("es")})`,
      href: `/panel/remediacion?evaluacion=${b.remediacion.evaluacion_id}&control=${b.remediacion.respuesta_id}`,
    });
  }
  return pasos;
}

/** Frase del estado del registro para el espacio de la empresa. */
export function textoEstadoRegistro(c: Pick<CumplimientoRegistro, "mapa" | "registro">): string {
  if (!c.mapa.iniciado) return "Aún no registras tu mapa de datos.";
  if (!c.registro.activas) return "Tu mapa está listo: registra tus actividades de tratamiento.";
  if (c.registro.vigente_completo) return "Tu registro está vigente y completo.";
  return `${c.registro.vigentes} de ${c.registro.activas} actividades vigentes · ${c.registro.completitud} % completo`;
}
