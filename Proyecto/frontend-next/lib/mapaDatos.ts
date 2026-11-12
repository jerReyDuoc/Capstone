/**
 * Mapa de datos personales (navegador → /bff/cliente/api/mapa-datos).
 *
 * El backend guarda el mapa, calcula las transferencias internacionales, los hallazgos y la
 * completitud, versiona cada cambio y genera el PDF. Aquí van las llamadas y la lógica pura de
 * presentación (probada en tests/mapa_datos.test.ts):
 *   - la disposición del diagrama (el mismo algoritmo por capas que usa el PDF del servidor);
 *   - los filtros del mapa navegable (dato sensible, NNA, transferencia, tercero, país, tipo);
 *   - la imagen PNG (un SVG en colores para papel, armado como texto escapado) y el CSV del
 *     inventario (con protección contra fórmulas de Excel).
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import { celdaCsv } from "@/lib/exportar";

export const BASE_MAPA = "/bff/cliente/api/mapa-datos";

/* ============================================================ tipos */

export type TipoElemento = "sistema" | "base_datos" | "tercero";
export type Severidad = "Crítica" | "Alta" | "Media" | "Baja";

export interface OpcionCatalogo {
  codigo: string;
  nombre: string;
  descripcion?: string;
  requiere_contrato?: boolean;
  valida?: boolean;
}

export interface CategoriaDatoApi {
  codigo: string;
  nombre: string;
  grupo: string;
  descripcion: string;
  ejemplos: string[];
  sensible: boolean;
}

export interface CategoriaTitularApi {
  codigo: string;
  nombre: string;
  descripcion: string;
  nna: boolean;
  posible_nna: boolean;
}

export interface CatalogoMapa {
  version: string;
  grupos_datos: string[];
  categorias_datos: CategoriaDatoApi[];
  categorias_titulares: CategoriaTitularApi[];
  tipos: OpcionCatalogo[];
  subtipos: Record<TipoElemento, OpcionCatalogo[]>;
  roles_tercero: OpcionCatalogo[];
  garantias: OpcionCatalogo[];
  frecuencias: OpcionCatalogo[];
  medios: OpcionCatalogo[];
  paises: { codigo: string; nombre: string }[];
  pais_local: string;
}

export type OrigenRegistro = "manual" | "plantilla" | "evaluacion";

export interface ElementoMapa {
  id: number;
  tipo: TipoElemento;
  nombre: string;
  subtipo: string | null;
  descripcion: string | null;
  proveedor: string | null;
  pais: string | null;
  responsable: string | null;
  categorias_datos: string[];
  categorias_titulares: string[];
  nna_declarado: boolean;
  incluye_nna: boolean;
  rol_tercero: string | null;
  contrato_firmado: boolean | null;
  origen: OrigenRegistro;
  clave: string | null;
  pendiente_revision: boolean;
  fecha_creacion: string | null;
  fecha_actualizacion: string | null;
  derivados: {
    sensibles: string[];
    incluye_nna: boolean;
    fuera_de_chile: boolean;
    pais_efectivo: string | null;
    flujos_entrantes: number;
    flujos_salientes: number;
  };
}

export interface FlujoMapa {
  id: number;
  origen_id: number;
  destino_id: number;
  finalidad: string | null;
  categorias_datos: string[];
  categorias_titulares: string[];
  nna_declarado: boolean;
  incluye_nna: boolean;
  frecuencia: string | null;
  medio: string | null;
  cifrado: boolean | null;
  garantia: string | null;
  origen: OrigenRegistro;
  clave: string | null;
  pendiente_revision: boolean;
  fecha_creacion: string | null;
  fecha_actualizacion: string | null;
  derivados: {
    internacional: boolean;
    pais_origen: string | null;
    pais_destino: string | null;
    hacia_tercero: boolean;
    desde_tercero: boolean;
    sensibles: string[];
    incluye_nna: boolean;
    garantia_valida: boolean;
  };
}

export interface HallazgoMapa {
  codigo: string;
  severidad: Severidad;
  titulo: string;
  detalle: string;
  recomendacion: string;
  referencia: string;
  elementos: number[];
  flujos: number[];
}

export interface ResumenMapa {
  sistemas: number;
  bases_datos: number;
  terceros: number;
  elementos: number;
  flujos: number;
  flujos_a_terceros: number;
  transferencias_internacionales: number;
  transferencias_sin_garantia: number;
  elementos_con_sensibles: number;
  flujos_con_sensibles: number;
  elementos_con_nna: number;
  fuera_de_chile: number;
  proveedores_ia: number;
  categorias_en_uso: number;
  categorias_sensibles_en_uso: number;
  titulares_en_uso: number;
  paises: { codigo: string; nombre: string; elementos: number }[];
  pendientes_revision: number;
}

export interface PendienteMapa {
  tipo: "elemento" | "flujo";
  id: number;
  nombre: string;
  faltan: string[];
  por_confirmar: boolean;
}

export interface VistaMapa {
  mapa: { version: number; fecha_actualizacion: string | null; iniciado: boolean; plantilla_inicial: string | null };
  elementos: ElementoMapa[];
  flujos: FlujoMapa[];
  resumen: ResumenMapa;
  hallazgos: HallazgoMapa[];
  conteo_hallazgos: Record<Severidad, number>;
  completitud: { porcentaje: number; pendientes: PendienteMapa[] };
  limites: { max_elementos: number; max_flujos: number };
  catalogo_version: string;
  /** Solo en las respuestas de un cambio: null si no había nada que guardar. */
  cambio?: { version: number; resumen: string; actividades_afectadas?: number } | null;
}

export interface PlantillaMapa {
  codigo: string;
  nombre: string;
  descripcion: string;
  recomendada: boolean;
  sistemas: number;
  bases_datos: number;
  terceros: number;
  flujos: number;
  elementos: { clave: string; tipo: TipoElemento; nombre: string }[];
}

export interface ExtremoSugerido {
  existente: boolean;
  id?: number;
  clave?: string;
  nombre: string;
}

export interface SugerenciaMapa {
  clave: string;
  titulo: string;
  motivo: string;
  descripcion: string;
  elementos: {
    clave: string;
    tipo: TipoElemento;
    subtipo: string;
    nombre: string;
    descripcion: string;
    pais: string | null;
    categorias_datos: string[];
    categorias_titulares: string[];
    rol_tercero: string | null;
  }[];
  flujos: { origen: ExtremoSugerido; destino: ExtremoSugerido; finalidad: string; categorias_datos: string[] }[];
  conector: string | null;
  candidatos: { id: number; nombre: string }[];
  usa_existente: number | null;
}

export interface SugerenciasApi {
  evaluacion_id: number | null;
  sin_evaluacion: boolean;
  sugerencias: SugerenciaMapa[];
  descartadas: number;
}

export interface CambioVersion {
  entidad: "elemento" | "flujo";
  operacion: "creado" | "editado" | "eliminado";
  id: number;
  nombre: string;
  tipo: TipoElemento | null;
  campos: string[];
}

export interface VersionMapa {
  numero: number;
  fecha: string;
  accion: string;
  resumen: string;
  elementos: number;
  flujos: number;
  huella: string;
  cambios_total: number;
  cambios?: CambioVersion[];
  contenido?: { elementos: ElementoMapa[]; flujos: FlujoMapa[] };
}

export interface ListaVersiones {
  items: VersionMapa[];
  total: number;
  pagina: number;
  paginas: number;
  version_actual: number;
}

export interface FiltrosMapa {
  sensibles: boolean;
  nna: boolean;
  internacional: boolean;
  tercero: number | null;
  pais: string | null;
  tipo: TipoElemento | null;
}

export const SIN_FILTROS: FiltrosMapa = { sensibles: false, nna: false, internacional: false, tercero: null, pais: null, tipo: null };

/** Campos que se pueden enviar al crear o editar (el backend rechaza cualquier otro). */
export interface DatosElemento {
  tipo?: TipoElemento;
  subtipo?: string | null;
  nombre?: string;
  descripcion?: string | null;
  proveedor?: string | null;
  pais?: string | null;
  responsable?: string | null;
  categorias_datos?: string[];
  categorias_titulares?: string[];
  nna_declarado?: boolean;
  rol_tercero?: string | null;
  contrato_firmado?: boolean | null;
  pendiente_revision?: boolean;
}

export interface DatosFlujo {
  origen_id?: number;
  destino_id?: number;
  finalidad?: string | null;
  categorias_datos?: string[];
  categorias_titulares?: string[];
  nna_declarado?: boolean;
  frecuencia?: string | null;
  medio?: string | null;
  cifrado?: boolean | null;
  garantia?: string | null;
  pendiente_revision?: boolean;
}

/* ============================================================ llamadas */

export const cargarCatalogoMapa = () => pedir<CatalogoMapa>(`${BASE_MAPA}/catalogo`);
export const cargarMapa = () => pedir<VistaMapa>(BASE_MAPA);

export const crearElemento = (version: number, datos: DatosElemento) =>
  pedir<VistaMapa>(`${BASE_MAPA}/elementos`, { method: "POST", json: { version, ...datos } });
export const editarElemento = (id: number, version: number, datos: DatosElemento) =>
  pedir<VistaMapa>(`${BASE_MAPA}/elementos/${id}`, { method: "PATCH", json: { version, ...datos } });
export const eliminarElemento = (id: number, version: number) =>
  pedir<VistaMapa>(`${BASE_MAPA}/elementos/${id}?version=${version}`, { method: "DELETE" });

export const crearFlujo = (version: number, datos: DatosFlujo) =>
  pedir<VistaMapa>(`${BASE_MAPA}/flujos`, { method: "POST", json: { version, ...datos } });
export const editarFlujo = (id: number, version: number, datos: DatosFlujo) =>
  pedir<VistaMapa>(`${BASE_MAPA}/flujos/${id}`, { method: "PATCH", json: { version, ...datos } });
export const eliminarFlujo = (id: number, version: number) =>
  pedir<VistaMapa>(`${BASE_MAPA}/flujos/${id}?version=${version}`, { method: "DELETE" });

export const confirmarRevision = (version: number, opciones: { todo?: boolean; elementos?: number[]; flujos?: number[] }) =>
  pedir<VistaMapa>(`${BASE_MAPA}/revision`, { method: "POST", json: { version, ...opciones } });

export const cargarPlantillasMapa = () => pedir<{ plantillas: PlantillaMapa[]; version: string }>(`${BASE_MAPA}/plantillas`);
export const aplicarPlantilla = (codigo: string, version: number) =>
  pedir<VistaMapa>(`${BASE_MAPA}/plantillas/aplicar`, { method: "POST", json: { codigo, version } });

export const cargarSugerencias = () => pedir<SugerenciasApi>(`${BASE_MAPA}/sugerencias`);
export const aceptarSugerencia = (clave: string, version: number, origenId: number | null) =>
  pedir<VistaMapa>(`${BASE_MAPA}/sugerencias/${encodeURIComponent(clave)}/aceptar`, {
    method: "POST",
    json: origenId ? { version, origen_id: origenId } : { version },
  });
export const descartarSugerencia = (clave: string) =>
  pedir<SugerenciasApi>(`${BASE_MAPA}/sugerencias/${encodeURIComponent(clave)}/descartar`, { method: "POST", json: {} });
export const restablecerSugerencias = () =>
  pedir<SugerenciasApi>(`${BASE_MAPA}/sugerencias/restablecer`, { method: "POST", json: {} });

export const cargarVersiones = (pagina = 1) => pedir<ListaVersiones>(`${BASE_MAPA}/versiones?pagina=${pagina}`);
export const cargarVersion = (numero: number) =>
  pedir<{ version: VersionMapa; es_actual: boolean; verificada: boolean }>(`${BASE_MAPA}/versiones/${numero}`);
export const restaurarVersion = (numero: number, version: number) =>
  pedir<VistaMapa>(`${BASE_MAPA}/versiones/${numero}/restaurar`, { method: "POST", json: { version } });

/** Parámetros de los filtros para el informe (mismos nombres que acepta el backend). */
export function queryFiltros(f: FiltrosMapa): string {
  const q = new URLSearchParams();
  if (f.sensibles) q.set("sensibles", "1");
  if (f.nna) q.set("nna", "1");
  if (f.internacional) q.set("internacional", "1");
  if (f.tercero) q.set("tercero", String(f.tercero));
  if (f.pais) q.set("pais", f.pais);
  if (f.tipo) q.set("tipo", f.tipo);
  const t = q.toString();
  return t ? `?${t}` : "";
}

export async function descargarInformeMapa(filtros: FiltrosMapa): Promise<{ blob: Blob; nombre: string }> {
  const res = await fetch(`${BASE_MAPA}/informe/pdf${queryFiltros(filtros)}`, { credentials: "same-origin", cache: "no-store" });
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
  return { blob: await res.blob(), nombre: m?.[1] ?? "mapa_datos_personales.pdf" };
}

export const enviarInformeMapa = (email: string, filtros: FiltrosMapa) =>
  pedir<{ enviado: boolean; destino: string; modo: string }>(`${BASE_MAPA}/informe/enviar`, {
    method: "POST",
    json: {
      ...(email.trim() ? { email: email.trim() } : {}),
      sensibles: filtros.sensibles,
      nna: filtros.nna,
      internacional: filtros.internacional,
      ...(filtros.tercero ? { tercero: filtros.tercero } : {}),
      ...(filtros.pais ? { pais: filtros.pais } : {}),
      ...(filtros.tipo ? { tipo: filtros.tipo } : {}),
    },
  });

/* ============================================================ textos */

export const ETIQUETA_TIPO: Record<TipoElemento, string> = {
  sistema: "Sistema",
  base_datos: "Base de datos",
  tercero: "Tercero",
};

export const ETIQUETA_TIPO_PLURAL: Record<TipoElemento, string> = {
  sistema: "Sistemas",
  base_datos: "Bases de datos",
  tercero: "Terceros",
};

export const ETIQUETA_ORIGEN: Record<OrigenRegistro, string> = {
  manual: "Agregado por tu empresa",
  plantilla: "Desde una plantilla",
  evaluacion: "Sugerido por tu evaluación",
};

export const SEVERIDADES: Severidad[] = ["Crítica", "Alta", "Media", "Baja"];

export const ETIQUETA_ACCION: Record<string, string> = {
  elemento_creado: "Elemento agregado",
  elemento_editado: "Elemento editado",
  elemento_eliminado: "Elemento eliminado",
  flujo_creado: "Flujo agregado",
  flujo_editado: "Flujo editado",
  flujo_eliminado: "Flujo eliminado",
  plantilla_aplicada: "Plantilla aplicada",
  sugerencia_aceptada: "Sugerencia aceptada",
  revision_confirmada: "Revisión confirmada",
  version_restaurada: "Versión restaurada",
};

export const ETIQUETA_CAMPO: Record<string, string> = {
  tipo: "tipo", subtipo: "categoría", nombre: "nombre", descripcion: "descripción", proveedor: "proveedor",
  pais: "país", responsable: "responsable interno", categorias_datos: "categorías de datos",
  categorias_titulares: "titulares", nna_declarado: "datos de NNA", rol_tercero: "rol", contrato_firmado: "contrato",
  pendiente_revision: "revisión", origen_id: "origen", destino_id: "destino", finalidad: "finalidad",
  frecuencia: "frecuencia", medio: "medio", cifrado: "cifrado", garantia: "garantía",
};

export function nombrePais(cat: CatalogoMapa | null, codigo: string | null | undefined): string {
  if (!codigo) return "Sin informar";
  return cat?.paises.find((p) => p.codigo === codigo)?.nombre ?? codigo;
}

export function nombreOpcion(lista: OpcionCatalogo[] | undefined, codigo: string | null | undefined): string {
  if (!codigo) return "—";
  return lista?.find((o) => o.codigo === codigo)?.nombre ?? codigo;
}

export function nombreSubtipo(cat: CatalogoMapa | null, tipo: TipoElemento, subtipo: string | null): string {
  return nombreOpcion(cat?.subtipos[tipo], subtipo);
}

export function nombreDato(cat: CatalogoMapa | null, codigo: string): string {
  return cat?.categorias_datos.find((c) => c.codigo === codigo)?.nombre ?? codigo;
}

export function esSensible(cat: CatalogoMapa | null, codigo: string): boolean {
  return Boolean(cat?.categorias_datos.find((c) => c.codigo === codigo)?.sensible);
}

export function nombreTitular(cat: CatalogoMapa | null, codigo: string): string {
  return cat?.categorias_titulares.find((c) => c.codigo === codigo)?.nombre ?? codigo;
}

/** "1 elemento" / "3 elementos". */
export const plural = (n: number, singular: string, varios: string) => `${n} ${n === 1 ? singular : varios}`;

/** Texto del aviso tras un cambio del mapa (suma las actividades del registro que volvieron a revisión). */
export function textoCambioMapa(resumen: string, actividadesAfectadas: number | undefined): string {
  if (!actividadesAfectadas) return resumen;
  return `${resumen} Revisa el registro de actividades: ${actividadesAfectadas === 1
    ? "1 actividad usa lo que cambiaste."
    : `${actividadesAfectadas} actividades usan lo que cambiaste.`}`;
}

/** Datos de contacto en un texto (el backend los rechaza: se avisa antes de enviar). */
export function contieneContacto(texto: string | null | undefined): boolean {
  if (!texto) return false;
  return (
    /[^\s@]+@[^\s@]+\.[A-Za-z]{2,}/.test(texto) ||
    /\b\d{1,2}\.?\d{3}\.?\d{3}\s?-\s?[\dkK]\b/.test(texto) ||
    /(?:\+?56[\s-]?)?\b9[\s-]?\d{4}[\s-]?\d{4}\b|\+\d[\d\s-]{8,}\d/.test(texto)
  );
}

/** Transferencia internacional entre dos países (mismo criterio que el backend). */
export function esInternacional(paisOrigen: string | null, paisDestino: string | null, local = "CL"): boolean {
  const origen = paisOrigen || local;
  return Boolean(paisDestino) && paisDestino !== local && paisDestino !== origen;
}

/* ============================================================ filtros del mapa navegable */

export function filtrosActivos(f: FiltrosMapa): number {
  return [f.sensibles, f.nna, f.internacional, f.tercero, f.pais, f.tipo].filter(Boolean).length;
}

/**
 * Ids de los elementos y flujos que cumplen TODOS los filtros activos (mismas reglas que el
 * informe PDF). Un flujo que cumple arrastra a sus dos extremos: nunca queda una flecha suelta.
 */
export function aplicarFiltros(vista: Pick<VistaMapa, "elementos" | "flujos">, f: FiltrosMapa): { elementos: Set<number>; flujos: Set<number> } {
  const { elementos, flujos } = vista;
  if (!filtrosActivos(f)) return { elementos: new Set(elementos.map((e) => e.id)), flujos: new Set(flujos.map((x) => x.id)) };
  const porId = new Map(elementos.map((e) => [e.id, e]));
  const vecinos = new Map<number, Set<number>>();
  const internacional = new Set<number>();
  for (const x of flujos) {
    if (!vecinos.has(x.origen_id)) vecinos.set(x.origen_id, new Set());
    if (!vecinos.has(x.destino_id)) vecinos.set(x.destino_id, new Set());
    vecinos.get(x.origen_id)!.add(x.destino_id);
    vecinos.get(x.destino_id)!.add(x.origen_id);
    if (x.derivados.internacional) {
      internacional.add(x.origen_id);
      internacional.add(x.destino_id);
    }
  }
  const okElemento = (e: ElementoMapa) =>
    (!f.sensibles || e.derivados.sensibles.length > 0) &&
    (!f.nna || e.incluye_nna) &&
    (!f.internacional || internacional.has(e.id) || e.derivados.fuera_de_chile) &&
    (!f.tercero || e.id === f.tercero || Boolean(vecinos.get(e.id)?.has(f.tercero))) &&
    (!f.pais || e.derivados.pais_efectivo === f.pais) &&
    (!f.tipo || e.tipo === f.tipo);
  const okFlujo = (x: FlujoMapa) =>
    (!f.sensibles || x.derivados.sensibles.length > 0) &&
    (!f.nna || x.incluye_nna) &&
    (!f.internacional || x.derivados.internacional) &&
    (!f.tercero || x.origen_id === f.tercero || x.destino_id === f.tercero) &&
    (!f.pais || x.derivados.pais_origen === f.pais || x.derivados.pais_destino === f.pais) &&
    (!f.tipo || porId.get(x.origen_id)?.tipo === f.tipo || porId.get(x.destino_id)?.tipo === f.tipo);
  const idsFlujos = new Set(flujos.filter(okFlujo).map((x) => x.id));
  const idsElementos = new Set(elementos.filter(okElemento).map((e) => e.id));
  for (const x of flujos) {
    if (idsFlujos.has(x.id)) {
      idsElementos.add(x.origen_id);
      idsElementos.add(x.destino_id);
    }
  }
  for (const id of [...idsElementos]) if (!porId.has(id)) idsElementos.delete(id);
  return { elementos: idsElementos, flujos: idsFlujos };
}

export function describirFiltros(f: FiltrosMapa, vista: Pick<VistaMapa, "elementos">, cat: CatalogoMapa | null): string {
  const partes: string[] = [];
  if (f.sensibles) partes.push("solo datos sensibles");
  if (f.nna) partes.push("solo datos de niños, niñas y adolescentes");
  if (f.internacional) partes.push("solo transferencias internacionales");
  if (f.tercero) partes.push(`tercero «${vista.elementos.find((e) => e.id === f.tercero)?.nombre ?? "?"}»`);
  if (f.pais) partes.push(`país ${nombrePais(cat, f.pais)}`);
  if (f.tipo) partes.push(`tipo ${ETIQUETA_TIPO[f.tipo].toLowerCase()}`);
  return partes.length ? partes.join(", ") : "sin filtros";
}

/* ============================================================ disposición del diagrama */

export const ANCHO_NODO = 200;
export const ALTO_NODO = 74;
export const ALTO_PASO = 10;
export const SEPARACION_X = 120;
export const SEPARACION_Y = 28;
export const SEPARACION_PASO = 12;
export const MARGEN = 24;
const ORDEN_TIPO: Record<string, number> = { sistema: 0, base_datos: 1, tercero: 2 };

export interface NodoDisposicion {
  id: number;
  columna: number;
  fila: number;
  x: number;
  y: number;
}

export interface Disposicion {
  nodos: Map<number, NodoDisposicion>;
  ancho: number;
  alto: number;
  columnas: number;
  /** id del flujo → puntos de paso { x de la columna, y central } en las columnas intermedias. */
  pasos: Map<number, { x: number; y: number }[]>;
}

/** Compara como Python (por puntos de código), para que el PDF y la pantalla ordenen igual. */
const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/**
 * Disposición por capas (Sugiyama), de izquierda a derecha en el sentido en que viajan los datos
 * (mismo algoritmo que app/domain/mapa_datos/disposicion.py): sin ciclos, columna = camino más
 * largo, terceros que solo reciben al final, puntos de paso para los flujos que saltan columnas
 * (la flecha pasa entre los nodos, no por detrás) y orden por baricentro para cruzar menos.
 */
export function calcularDisposicion(
  elementos: { id: number; tipo: string; nombre: string }[],
  flujos: { id: number; origen_id: number; destino_id: number }[],
): Disposicion {
  const orden = [...elementos].sort(
    (a, b) => (ORDEN_TIPO[a.tipo] ?? 9) - (ORDEN_TIPO[b.tipo] ?? 9) || cmp(a.nombre.toLowerCase(), b.nombre.toLowerCase()) || a.id - b.id,
  );
  const ids = orden.map((e) => e.id);
  const tipo = new Map(orden.map((e) => [e.id, e.tipo]));
  const existe = new Set(ids);
  const validos = [...flujos]
    .sort((a, b) => a.id - b.id || a.origen_id - b.origen_id || a.destino_id - b.destino_id)
    .filter((f) => existe.has(f.origen_id) && existe.has(f.destino_id) && f.origen_id !== f.destino_id);
  const sucesores = new Map<number, number[]>(ids.map((v) => [v, []]));
  for (const f of validos) {
    const lista = sucesores.get(f.origen_id)!;
    if (!lista.includes(f.destino_id)) lista.push(f.destino_id);
  }

  // 1. DAG sin las aristas que cierran un ciclo (DFS iterativo, determinista)
  const estado = new Map<number, 1 | 2>();
  const dag = new Map<number, number[]>(ids.map((v) => [v, []]));
  for (const raiz of ids) {
    if (estado.has(raiz)) continue;
    const pila: { v: number; i: number }[] = [{ v: raiz, i: 0 }];
    estado.set(raiz, 1);
    while (pila.length) {
      const tope = pila[pila.length - 1];
      const hijos = sucesores.get(tope.v)!;
      if (tope.i >= hijos.length) {
        estado.set(tope.v, 2);
        pila.pop();
        continue;
      }
      const w = hijos[tope.i++];
      if (estado.get(w) === 1) continue;
      dag.get(tope.v)!.push(w);
      if (!estado.has(w)) {
        estado.set(w, 1);
        pila.push({ v: w, i: 0 });
      }
    }
  }

  // 2. columna = camino más largo (Kahn)
  const entrada = new Map<number, number>(ids.map((v) => [v, 0]));
  for (const v of ids) for (const w of dag.get(v)!) entrada.set(w, entrada.get(w)! + 1);
  const columna = new Map<number, number>(ids.map((v) => [v, 0]));
  const cola = ids.filter((v) => entrada.get(v) === 0);
  for (let k = 0; k < cola.length; k++) {
    const v = cola[k];
    for (const w of dag.get(v)!) {
      columna.set(w, Math.max(columna.get(w)!, columna.get(v)! + 1));
      entrada.set(w, entrada.get(w)! - 1);
      if (entrada.get(w) === 0) cola.push(w);
    }
  }
  const conectados = new Set<number>();
  for (const v of ids) {
    if (sucesores.get(v)!.length) conectados.add(v);
    for (const w of sucesores.get(v)!) conectados.add(w);
  }
  let maxima = 0;
  for (const v of conectados) maxima = Math.max(maxima, columna.get(v)!);
  if (!conectados.size) maxima = ids.reduce((m, v) => Math.max(m, ORDEN_TIPO[tipo.get(v)!] ?? 0), 0);
  for (const v of ids) {
    const t = tipo.get(v)!;
    if (!conectados.has(v)) columna.set(v, t !== "tercero" ? Math.min(ORDEN_TIPO[t] ?? 0, maxima) : maxima);
    else if (t === "tercero" && !dag.get(v)!.length) columna.set(v, maxima);
  }

  // 3. puntos de paso de los flujos que saltan columnas
  const col = new Map<string, number>(ids.map((v) => [`e${v}`, columna.get(v)!]));
  const suc = new Map<string, string[]>();
  const pred = new Map<string, string[]>();
  const agregar = (m: Map<string, string[]>, k: string, v: string) => {
    if (!m.has(k)) m.set(k, []);
    m.get(k)!.push(v);
  };
  const virtualesDe = new Map<number, string[]>();
  for (const f of validos) {
    const co = columna.get(f.origen_id)!;
    const cd = columna.get(f.destino_id)!;
    const cadena = [`e${f.origen_id}`];
    if (cd - co > 1) {
      const intermedios: string[] = [];
      for (let c = co + 1; c < cd; c++) {
        const k = `v${f.id}-${c}`;
        col.set(k, c);
        intermedios.push(k);
      }
      virtualesDe.set(f.id, intermedios);
      cadena.push(...intermedios);
    }
    cadena.push(`e${f.destino_id}`);
    for (let i = 0; i < cadena.length - 1; i++) {
      agregar(suc, cadena[i], cadena[i + 1]);
      agregar(pred, cadena[i + 1], cadena[i]);
    }
  }

  // 4. orden por baricentro (4 barridos)
  const total = ids.length ? Math.max(...ids.map((v) => columna.get(v)!)) + 1 : 0;
  const capas: string[][] = Array.from({ length: total }, () => []);
  for (const v of ids) capas[columna.get(v)!].push(`e${v}`);
  for (const fid of [...virtualesDe.keys()].sort((a, b) => a - b)) {
    for (const k of virtualesDe.get(fid)!) capas[col.get(k)!].push(k);
  }
  for (let barrido = 0; barrido < 4; barrido++) {
    const derecha = barrido % 2 === 0;
    const rango: number[] = [];
    if (derecha) for (let c = 1; c < total; c++) rango.push(c);
    else for (let c = total - 2; c >= 0; c--) rango.push(c);
    for (const c of rango) {
      const pos = new Map<string, number>();
      capas.forEach((capa) => capa.forEach((k, i) => pos.set(k, i)));
      const vecinos = derecha ? pred : suc;
      const claves = capas[c].map((k, i) => {
        const ref = (vecinos.get(k) ?? []).filter((w) => pos.has(w) && col.get(w) !== c).map((w) => pos.get(w)!);
        return { k, b: ref.length ? ref.reduce((s2, x) => s2 + x, 0) / ref.length : i, i };
      });
      claves.sort((a, b) => a.b - b.b || a.i - b.i);
      capas[c] = claves.map((x) => x.k);
    }
  }

  // 5. coordenadas (alturas variables: nodos y puntos de paso)
  const esNodo = (k: string) => k.startsWith("e");
  const altoItem = (k: string) => (esNodo(k) ? ALTO_NODO : ALTO_PASO);
  const separacion = (a: string, b: string) => (esNodo(a) && esNodo(b) ? SEPARACION_Y : SEPARACION_PASO);
  const altoCapa = (capa: string[]) =>
    capa.reduce((t, k) => t + altoItem(k), 0) + capa.slice(1).reduce((t, k, i) => t + separacion(capa[i], k), 0);
  const altoMax = capas.reduce((m, capa) => Math.max(m, altoCapa(capa)), 0);
  const altoTotal = MARGEN * 2 + altoMax;
  const nodos = new Map<number, NodoDisposicion>();
  const centroPaso = new Map<string, { x: number; y: number }>();
  capas.forEach((capa, c) => {
    const x = MARGEN + c * (ANCHO_NODO + SEPARACION_X);
    let y = MARGEN + (altoMax - altoCapa(capa)) / 2;
    let fila = 0;
    capa.forEach((k, i) => {
      if (i) y += separacion(capa[i - 1], k);
      if (esNodo(k)) {
        const v = Number(k.slice(1));
        nodos.set(v, { id: v, columna: c, fila: fila++, x, y });
      } else {
        centroPaso.set(k, { x, y: y + ALTO_PASO / 2 });
      }
      y += altoItem(k);
    });
  });
  const pasos = new Map<number, { x: number; y: number }[]>();
  for (const [fid, ks] of virtualesDe) pasos.set(fid, ks.map((k) => centroPaso.get(k)!));
  const ancho = MARGEN * 2 + Math.max(0, total * (ANCHO_NODO + SEPARACION_X) - SEPARACION_X);
  return { nodos, ancho, alto: altoTotal, columnas: total, pasos };
}

/**
 * Curva de un flujo: de la derecha del origen a la izquierda del destino, pasando por los puntos
 * de paso de las columnas intermedias (o rodeando por fuera si va hacia atrás).
 */
export function rutaFlujo(
  o: NodoDisposicion,
  d: NodoDisposicion,
  desfase = 0,
  pasos: { x: number; y: number }[] = [],
): { d: string; punta: { x: number; y: number; haciaIzquierda: boolean }; medio: { x: number; y: number } } {
  const y1 = o.y + ALTO_NODO / 2 + desfase;
  const y2 = d.y + ALTO_NODO / 2 + desfase;
  const x1 = o.x + ANCHO_NODO;
  if (d.columna <= o.columna) {
    const x2 = d.x + ANCHO_NODO;
    const curva = Math.max(x1, x2) + 70;
    return {
      d: `M ${x1} ${y1} C ${curva} ${y1}, ${curva} ${y2}, ${x2 + 8} ${y2}`,
      punta: { x: x2, y: y2, haciaIzquierda: true },
      medio: { x: curva - 18, y: (y1 + y2) / 2 },
    };
  }
  const x2 = d.x;
  let cx = x1;
  let cy = y1;
  let ruta = `M ${x1} ${y1}`;
  for (const p of pasos) {
    const dx = Math.max(30, (p.x - cx) / 2);
    ruta += ` C ${cx + dx} ${cy}, ${p.x - dx} ${p.y}, ${p.x} ${p.y} L ${p.x + ANCHO_NODO} ${p.y}`;
    cx = p.x + ANCHO_NODO;
    cy = p.y;
  }
  const dx = Math.max(30, (x2 - cx) / 2);
  ruta += ` C ${cx + dx} ${cy}, ${x2 - dx} ${y2}, ${x2 - 8} ${y2}`;
  const medio = pasos.length ? { x: pasos[0].x + ANCHO_NODO / 2, y: pasos[0].y } : { x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
  return { d: ruta, punta: { x: x2, y: y2, haciaIzquierda: false }, medio };
}

/** Desfase vertical para que dos flujos entre el mismo par de elementos no se encimen. */
export function desfasesFlujos(flujos: { id: number; origen_id: number; destino_id: number }[]): Map<number, number> {
  const cuenta = new Map<string, number>();
  const salida = new Map<number, number>();
  for (const f of [...flujos].sort((a, b) => a.id - b.id)) {
    const clave = `${Math.min(f.origen_id, f.destino_id)}-${Math.max(f.origen_id, f.destino_id)}`;
    const n = cuenta.get(clave) ?? 0;
    cuenta.set(clave, n + 1);
    salida.set(f.id, n === 0 ? 0 : n % 2 ? 10 * Math.ceil(n / 2) : -10 * Math.ceil(n / 2));
  }
  return salida;
}

/** Parte un nombre en hasta `lineas` líneas de `ancho` caracteres (la última termina en "…"). */
export function partirTexto(texto: string, ancho: number, lineas = 2): string[] {
  const palabras = texto.trim().split(/\s+/);
  const salida: string[] = [];
  let actual = "";
  let i = 0;
  for (; i < palabras.length; i++) {
    const p = palabras[i];
    if ((actual ? actual.length + 1 : 0) + p.length <= ancho) {
      actual = actual ? `${actual} ${p}` : p;
    } else {
      if (actual) salida.push(actual);
      actual = p;
      if (salida.length === lineas) break;
    }
  }
  if (actual && salida.length < lineas) salida.push(actual);
  const recortar = (s: string) => (s.length > ancho ? `${s.slice(0, ancho - 1).trimEnd()}…` : s);
  const usado = salida.join(" ").length;
  if (usado < texto.trim().length && salida.length) {
    const ultima = salida.length - 1;
    salida[ultima] = recortar(`${salida[ultima]} ${texto.trim().slice(usado).trim()}`);
    if (!salida[ultima].endsWith("…")) salida[ultima] = recortar(`${salida[ultima]}…`);
  }
  return salida.map(recortar);
}

/* ============================================================ exportación PNG (SVG para papel) */

const PAPEL = {
  fondo: "#ffffff",
  tinta: "#14201b",
  gris: "#5b6b64",
  linea: "#d5ddd9",
  verde: "#0b7a5a",
  flujo: "#7d8b85",
  sensible: "#b4233f",
  internacional: "#9a6a00",
  nna: "#6b3fa0",
  tipos: {
    sistema: { relleno: "#e3f4ee", borde: "#0b7a5a" },
    base_datos: { relleno: "#e8ecfb", borde: "#3d4fa8" },
    tercero: { relleno: "#fdf0e4", borde: "#b3541e" },
  } as Record<TipoElemento, { relleno: string; borde: string }>,
};

export function escaparXml(texto: string): string {
  return texto.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/**
 * SVG del mapa (con los filtros aplicados) en colores para papel, con título, leyenda y pie.
 * Todo lo que escribió el usuario va escapado: el SVG se arma como texto.
 */
export function svgParaExportar(
  vista: Pick<VistaMapa, "elementos" | "flujos" | "mapa">,
  filtros: FiltrosMapa,
  opciones: { empresa?: string; descripcionFiltros?: string; fecha?: Date } = {},
): { svg: string; ancho: number; alto: number } {
  const visibles = aplicarFiltros(vista, filtros);
  const elementos = vista.elementos.filter((e) => visibles.elementos.has(e.id));
  const flujos = vista.flujos.filter((f) => visibles.flujos.has(f.id));
  const lay = calcularDisposicion(elementos, flujos);
  const cabecera = 78;
  const pie = 56;
  const ancho = Math.max(lay.ancho, 760);
  const alto = cabecera + Math.max(lay.alto, 120) + pie;
  const dx = (ancho - lay.ancho) / 2;
  const desfases = desfasesFlujos(flujos);
  const partes: string[] = [];
  const fecha = (opciones.fecha ?? new Date()).toLocaleString("es-CL", { timeZone: "America/Santiago" });

  partes.push(`<rect width="${ancho}" height="${alto}" fill="${PAPEL.fondo}"/>`);
  partes.push(`<rect x="0" y="0" width="${ancho}" height="4" fill="${PAPEL.verde}"/>`);
  partes.push(`<text x="24" y="34" font-size="20" font-weight="700" fill="${PAPEL.tinta}">Mapa de datos personales${opciones.empresa ? ` · ${escaparXml(opciones.empresa)}` : ""}</text>`);
  partes.push(`<text x="24" y="56" font-size="12" fill="${PAPEL.gris}">Versión ${vista.mapa.version} · ${escaparXml(fecha)} · Vista: ${escaparXml(opciones.descripcionFiltros ?? "sin filtros")} · ${elementos.length} elementos y ${flujos.length} flujos</text>`);
  partes.push(`<g transform="translate(${dx} ${cabecera})">`);
  for (const f of flujos) {
    const o = lay.nodos.get(f.origen_id);
    const d = lay.nodos.get(f.destino_id);
    if (!o || !d) continue;
    const r = rutaFlujo(o, d, desfases.get(f.id) ?? 0, lay.pasos.get(f.id));
    const color = f.derivados.internacional ? PAPEL.internacional : f.derivados.sensibles.length ? PAPEL.sensible : PAPEL.flujo;
    const grosor = f.derivados.internacional || f.derivados.sensibles.length ? 2.2 : 1.5;
    partes.push(`<path d="${r.d}" fill="none" stroke="${color}" stroke-width="${grosor}"${f.derivados.internacional ? ' stroke-dasharray="6 4"' : ""}/>`);
    const s = r.punta.haciaIzquierda ? 1 : -1;
    partes.push(`<path d="M ${r.punta.x} ${r.punta.y} L ${r.punta.x + 10 * s} ${r.punta.y - 5} L ${r.punta.x + 10 * s} ${r.punta.y + 5} Z" fill="${color}"/>`);
  }
  for (const e of elementos) {
    const n = lay.nodos.get(e.id)!;
    const c = PAPEL.tipos[e.tipo];
    partes.push(`<g transform="translate(${n.x} ${n.y})">`);
    partes.push(`<rect width="${ANCHO_NODO}" height="${ALTO_NODO}" rx="10" fill="${c.relleno}" stroke="${c.borde}" stroke-width="${e.derivados.sensibles.length ? 2 : 1.2}"/>`);
    partes.push(`<rect x="0" y="8" width="4" height="${ALTO_NODO - 16}" rx="2" fill="${c.borde}"/>`);
    partes.push(`<text x="14" y="16" font-size="9" font-weight="700" letter-spacing="0.6" fill="${c.borde}">${escaparXml(ETIQUETA_TIPO[e.tipo].toUpperCase())}</text>`);
    partirTexto(e.nombre, 26, 2).forEach((linea, i) => {
      partes.push(`<text x="14" y="${32 + i * 14}" font-size="12.5" font-weight="700" fill="${PAPEL.tinta}">${escaparXml(linea)}</text>`);
    });
    const pais = e.derivados.pais_efectivo ?? "¿país?";
    partes.push(`<text x="14" y="${ALTO_NODO - 8}" font-size="10" font-weight="700" fill="${e.derivados.fuera_de_chile ? PAPEL.internacional : PAPEL.gris}">${escaparXml(pais)}</text>`);
    let xm = ANCHO_NODO - 8;
    const marcas: [string, string][] = [];
    if (e.derivados.sensibles.length) marcas.push(["SENSIBLE", PAPEL.sensible]);
    if (e.incluye_nna) marcas.push(["NNA", PAPEL.nna]);
    for (const [texto, color] of marcas) {
      const largo = texto.length * 6.2 + 12;
      xm -= largo;
      partes.push(`<rect x="${xm}" y="${ALTO_NODO - 20}" width="${largo}" height="14" rx="7" fill="${color}"/>`);
      partes.push(`<text x="${xm + 6}" y="${ALTO_NODO - 10}" font-size="8.5" font-weight="700" fill="#ffffff">${texto}</text>`);
      xm -= 4;
    }
    partes.push(`</g>`);
  }
  partes.push(`</g>`);
  // Leyenda
  const yL = alto - pie + 22;
  let xL = 24;
  for (const t of ["sistema", "base_datos", "tercero"] as TipoElemento[]) {
    partes.push(`<rect x="${xL}" y="${yL - 10}" width="16" height="12" rx="3" fill="${PAPEL.tipos[t].relleno}" stroke="${PAPEL.tipos[t].borde}"/>`);
    partes.push(`<text x="${xL + 22}" y="${yL}" font-size="11" fill="${PAPEL.tinta}">${ETIQUETA_TIPO[t]}</text>`);
    xL += 120;
  }
  for (const [texto, color, guion] of [
    ["Flujo", PAPEL.flujo, ""],
    ["Con datos sensibles", PAPEL.sensible, ""],
    ["Transferencia internacional", PAPEL.internacional, ' stroke-dasharray="6 4"'],
  ] as const) {
    partes.push(`<line x1="${xL}" y1="${yL - 4}" x2="${xL + 26}" y2="${yL - 4}" stroke="${color}" stroke-width="2.2"${guion}/>`);
    partes.push(`<text x="${xL + 32}" y="${yL}" font-size="11" fill="${PAPEL.tinta}">${texto}</text>`);
    xL += 48 + texto.length * 6;
  }
  partes.push(`<text x="24" y="${alto - 10}" font-size="10" fill="${PAPEL.gris}">ComplianceIA de Therion Labs · Herramienta de apoyo a la gestión: no constituye asesoría legal.</text>`);

  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${ancho}" height="${alto}" viewBox="0 0 ${ancho} ${alto}" ` +
    `font-family="Inter, 'Segoe UI', Arial, Helvetica, sans-serif">${partes.join("")}</svg>`;
  return { svg, ancho, alto };
}

/** Convierte el SVG a PNG (escala 2× para que se lea bien impreso o en una presentación). */
export async function svgAPng(svg: string, ancho: number, alto: number, escala = 2): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const img = new Image();
    img.decoding = "async";
    await new Promise<void>((ok, falla) => {
      img.onload = () => ok();
      img.onerror = () => falla(new Error("No se pudo dibujar la imagen"));
      img.src = url;
    });
    const lienzo = document.createElement("canvas");
    lienzo.width = Math.ceil(ancho * escala);
    lienzo.height = Math.ceil(alto * escala);
    const ctx = lienzo.getContext("2d");
    if (!ctx) throw new Error("El navegador no permite generar imágenes");
    ctx.scale(escala, escala);
    ctx.drawImage(img, 0, 0, ancho, alto);
    return await new Promise<Blob>((ok, falla) =>
      lienzo.toBlob((b) => (b ? ok(b) : falla(new Error("No se pudo generar la imagen"))), "image/png"),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

/* ============================================================ CSV del inventario */

/**
 * Inventario en CSV (una fila por elemento y por flujo), separador ";" y BOM para Excel en
 * es-CL. Sirve para llevarlo a una planilla o al registro de actividades de tratamiento.
 */
export function csvInventario(vista: Pick<VistaMapa, "elementos" | "flujos">, cat: CatalogoMapa | null): string {
  const porId = new Map(vista.elementos.map((e) => [e.id, e]));
  const lista = (codigos: string[], f: (c: string) => string) => codigos.map(f).join(", ");
  const cabecera = [
    "Registro", "Nombre u origen", "Destino", "Tipo", "Categoría", "Proveedor", "País", "Responsable interno",
    "Categorías de datos", "Datos sensibles", "Titulares", "Incluye NNA", "Rol del tercero", "Contrato firmado",
    "Finalidad", "Frecuencia", "Medio", "Cifrado", "Transferencia internacional", "Garantía", "Por confirmar",
  ];
  const siNo = (v: boolean | null) => (v === null ? "Por confirmar" : v ? "Sí" : "No");
  const filas: (string | number | null)[][] = [];
  for (const e of vista.elementos) {
    filas.push([
      "Elemento", e.nombre, "", ETIQUETA_TIPO[e.tipo], nombreSubtipo(cat, e.tipo, e.subtipo), e.proveedor ?? "",
      nombrePais(cat, e.derivados.pais_efectivo), e.responsable ?? "", lista(e.categorias_datos, (c) => nombreDato(cat, c)),
      lista(e.derivados.sensibles, (c) => nombreDato(cat, c)), lista(e.categorias_titulares, (c) => nombreTitular(cat, c)),
      e.incluye_nna ? "Sí" : "No", e.tipo === "tercero" ? nombreOpcion(cat?.roles_tercero, e.rol_tercero) : "",
      e.tipo === "tercero" ? siNo(e.contrato_firmado) : "", "", "", "", "", "", "", e.pendiente_revision ? "Sí" : "No",
    ]);
  }
  for (const f of vista.flujos) {
    filas.push([
      "Flujo", porId.get(f.origen_id)?.nombre ?? "", porId.get(f.destino_id)?.nombre ?? "", "", "", "", "", "",
      lista(f.categorias_datos, (c) => nombreDato(cat, c)), lista(f.derivados.sensibles, (c) => nombreDato(cat, c)),
      lista(f.categorias_titulares, (c) => nombreTitular(cat, c)), f.incluye_nna ? "Sí" : "No", "", "",
      f.finalidad ?? "", nombreOpcion(cat?.frecuencias, f.frecuencia), nombreOpcion(cat?.medios, f.medio), siNo(f.cifrado),
      f.derivados.internacional ? `Sí (${nombrePais(cat, f.derivados.pais_origen)} → ${nombrePais(cat, f.derivados.pais_destino)})` : "No",
      f.garantia ? nombreOpcion(cat?.garantias, f.garantia) : "", f.pendiente_revision ? "Sí" : "No",
    ]);
  }
  const lineas = [cabecera, ...filas].map((fila) => fila.map((v) => celdaCsv(v === "" ? null : v)).join(";"));
  return `﻿${lineas.join("\r\n")}`;
}

/** Mensaje para el usuario a partir de un error del BFF. */
export function mensajeError(e: unknown, porDefecto: string): string {
  if (e instanceof ErrorBff) {
    if (e.info.mensaje) return e.info.mensaje;
    if (e.status === 0) return "No hay conexión con el servidor. Revisa tu conexión e inténtalo de nuevo.";
    if (e.status === 429) return "Hiciste muchos intentos seguidos. Espera un momento e inténtalo de nuevo.";
  }
  return porDefecto;
}
