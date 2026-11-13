/**
 * Asistente de registro (navegador → /bff/cliente/api/asistente).
 *
 * Una entrevista guiada por áreas propone sistemas, flujos y actividades para el mapa de datos y el
 * registro de actividades. Nada se guarda sin que el usuario lo acepte (tal cual o editado) y cada
 * propuesta muestra con qué modelo y versión de la guía se hizo. Si la ayuda automática no está
 * disponible, la entrevista sigue igual y todo se completa a mano.
 *
 * Aquí solo hay llamadas y lógica de presentación pura (probada en tests/asistente.test.ts).
 */
import { pedir } from "@/lib/encuesta/cliente";
import type { CatalogoMapa } from "@/lib/mapaDatos";
import type { CatalogoRat } from "@/lib/registroActividades";

export const BASE_ASISTENTE = "/bff/cliente/api/asistente";

export type CodigoArea = "personas" | "clientes" | "proveedores" | "marketing" | "ti" | "ia";
export type TipoPropuesta = "elemento" | "flujo" | "actividad";
export type EstadoPropuesta = "sugerida" | "aceptada" | "editada" | "descartada" | "caducada";
export type MotivoDescarte = "no_aplica" | "incorrecta" | "duplicada" | "otro";
export type Severidad = "Crítica" | "Alta" | "Media" | "Baja";

export interface PreguntaApi {
  codigo: string;
  texto: string;
  ayuda: string;
  ejemplos: string[];
}

export interface AreaApi {
  codigo: CodigoArea;
  nombre: string;
  descripcion: string;
  preguntas: number;
  completada?: boolean;
  actual?: boolean;
}

export interface SesionApi {
  id: number;
  estado: "activa" | "cerrada";
  area_actual: CodigoArea;
  area_nombre: string;
  paso: number;
  total_pasos: number;
  areas: AreaApi[];
  pregunta: PreguntaApi | null;
  terminada: boolean;
  fecha_actualizacion: string | null;
}

export interface MensajeApi {
  id: number;
  rol: "asistente" | "usuario";
  area: string | null;
  pregunta_codigo: string | null;
  contenido: string;
  bloqueado: boolean;
  motivo_sin_ia: string | null;
  fecha: string | null;
}

export interface InconsistenciaApi {
  codigo: "sensible_sin_base" | "transferencia_sin_garantia" | "actividad_sin_plazo" | "flujo_sin_actividad";
  severidad: Severidad;
  texto: string;
  referencia: { tipo: "propuesta" | "flujo" | "actividad"; id?: number; clave?: string } | null;
}

export interface PlazoPropuesta {
  categoria: string;
  plazo: number | null;
  unidad: string | null;
  desde: string | null;
  fundamento: string | null;
}

/** Campos posibles de una propuesta (cada tipo usa los suyos). */
export interface PayloadPropuesta {
  tipo?: string | null;
  subtipo?: string | null;
  nombre?: string | null;
  descripcion?: string | null;
  proveedor?: string | null;
  pais?: string | null;
  responsable?: string | null;
  categorias_datos?: string[];
  categorias_titulares?: string[];
  rol_tercero?: string | null;
  contrato_firmado?: boolean | null;
  origen?: string | null;
  destino?: string | null;
  finalidad?: string | null;
  frecuencia?: string | null;
  medio?: string | null;
  cifrado?: boolean | null;
  garantia?: string | null;
  area?: string | null;
  elementos?: string[];
  flujos?: string[];
  finalidades?: string[];
  fuentes?: { tipo: string; detalle: string | null }[];
  base_licitud?: string | null;
  interes_legitimo?: string | null;
  base_sensibles?: string | null;
  plazos?: PlazoPropuesta[];
  decisiones?: { existe: boolean | null };
  medidas?: { codigos: string[]; otras: string | null };
  rol?: string | null;
}

export interface PropuestaApi {
  id: number;
  tipo: TipoPropuesta;
  clave: string;
  estado: EstadoPropuesta;
  origen: "entrevista" | "documento" | "sin_ia";
  area: string | null;
  nombre: string | null;
  payload: PayloadPropuesta;
  payload_final: PayloadPropuesta | null;
  campos_editados: string[];
  explicaciones: Record<string, string>;
  inconsistencias: InconsistenciaApi[];
  riesgo_nivel: string | null;
  confianza: "alta" | "media" | "baja";
  ia: { modelo: string; prompt_version: string; traza_id: string | null; etiqueta: string | null };
  entidad_destino: string | null;
  entidad_destino_id: number | null;
  motivo_descarte: MotivoDescarte | null;
  documento_id: number | null;
  fecha_creacion: string | null;
  fecha_decision: string | null;
}

export interface DocumentoApi {
  id: number;
  nombre_archivo: string;
  tipo_documento: string;
  tipo_documento_nombre: string;
  estado: "listo" | "bloqueado" | "ilegible" | "rechazado_pii" | "sin_texto" | "sin_ia";
  lineas_omitidas: number;
  pasajes_usados: number | null;
  pasajes_total: number | null;
  motivo_sin_ia: string | null;
  fecha: string | null;
}

export interface CuotaAsistente {
  usados: number;
  limite: number | null;
  restantes: number | null;
}

export interface EstadoAsistente {
  sesion: SesionApi | null;
  mensajes: MensajeApi[];
  propuestas: PropuestaApi[];
  pendientes: number;
  referencias: { elementos: Record<string, string>; flujos: Record<string, string> };
  documentos: DocumentoApi[];
  revision: InconsistenciaApi[];
  mapa: { version: number; elementos: number; flujos: number; actividades: number };
  areas: AreaApi[];
  ia: { habilitada: boolean; cuota: { reinicia_en: string; respuestas: CuotaAsistente; documentos: CuotaAsistente } };
  limites: { max_caracteres: number; max_mb_documento: number; max_pendientes: number };
  /** Solo en las respuestas de una acción. */
  nuevas?: number[];
  aviso?: string | null;
  bloqueado?: boolean;
  documento?: DocumentoApi;
}

/* ------------------------------------------------------------ llamadas */

export const cargarAsistente = () => pedir<EstadoAsistente>(BASE_ASISTENTE);

export const iniciarEntrevista = (area?: CodigoArea) =>
  pedir<EstadoAsistente>(`${BASE_ASISTENTE}/sesiones`, { method: "POST", json: area ? { area } : {} });

export const cambiarArea = (sesionId: number, area: CodigoArea) =>
  pedir<EstadoAsistente>(`${BASE_ASISTENTE}/sesiones/${sesionId}/area`, { method: "POST", json: { area } });

/** Nunca se reintenta: puede llamar al servicio de IA y gastar cuota. */
export const responderPregunta = (sesionId: number, texto: string, omitir = false, sinIa = false) =>
  pedir<EstadoAsistente>(`${BASE_ASISTENTE}/sesiones/${sesionId}/respuestas`, {
    method: "POST",
    json: omitir ? { omitir: true } : sinIa ? { texto, sin_ia: true } : { texto },
  }, { reintentos: 0 });

/** La ayuda automática falló por algo pasajero: la pregunta no avanzó y se puede reintentar o guardar sin ayuda. */
export const CODIGO_AYUDA_NO_DISPONIBLE = "AYUDA_NO_DISPONIBLE";

export const cerrarEntrevista = (sesionId: number) =>
  pedir<EstadoAsistente>(`${BASE_ASISTENTE}/sesiones/${sesionId}/cerrar`, { method: "POST", json: {} });

export async function subirDocumento(archivo: File, sesionId: number | null): Promise<EstadoAsistente> {
  const form = new FormData();
  form.append("file", archivo, archivo.name);
  if (sesionId) form.append("sesion_id", String(sesionId));
  return pedir<EstadoAsistente>(`${BASE_ASISTENTE}/documentos`, { method: "POST", body: form }, { reintentos: 0 });
}

export const aceptarPropuesta = (id: number, versionMapa: number, payload?: PayloadPropuesta) =>
  pedir<EstadoAsistente>(`${BASE_ASISTENTE}/propuestas/${id}/aceptar`, {
    method: "POST",
    json: payload ? { payload, version_mapa: versionMapa } : { version_mapa: versionMapa },
  }, { reintentos: 0 });

export const descartarPropuesta = (id: number, motivo: MotivoDescarte) =>
  pedir<EstadoAsistente>(`${BASE_ASISTENTE}/propuestas/${id}/descartar`, { method: "POST", json: { motivo } });

/* ------------------------------------------------------------ presentación */

export const MOTIVOS_DESCARTE: { codigo: MotivoDescarte; nombre: string }[] = [
  { codigo: "no_aplica", nombre: "No aplica a mi empresa" },
  { codigo: "incorrecta", nombre: "Está mal" },
  { codigo: "duplicada", nombre: "Ya existe" },
  { codigo: "otro", nombre: "Otro motivo" },
];

export const ETIQUETA_ESTADO: Record<EstadoPropuesta, string> = {
  sugerida: "Por revisar",
  aceptada: "Aceptada",
  editada: "Aceptada con cambios",
  descartada: "Descartada",
  caducada: "Ya no aplica",
};

export const ETIQUETA_INCONSISTENCIA: Record<InconsistenciaApi["codigo"], string> = {
  sensible_sin_base: "Dato sensible sin base legal",
  transferencia_sin_garantia: "Envío fuera de Chile sin garantía",
  actividad_sin_plazo: "Falta cuánto tiempo se guardan los datos",
  flujo_sin_actividad: "Envío de datos sin actividad en el registro",
};

export const AVISO_DOCUMENTO: Record<DocumentoApi["estado"], string> = {
  listo: "Leído",
  bloqueado: "No se pudo procesar",
  ilegible: "No se pudo leer",
  rechazado_pii: "Parece una lista de personas",
  sin_texto: "Sin texto legible",
  sin_ia: "Leído sin ayuda automática",
};

const TIPO_ELEMENTO: Record<string, string> = { sistema: "Sistema", base_datos: "Base de datos", tercero: "Tercero" };

export function tituloTipo(p: Pick<PropuestaApi, "tipo" | "payload">): string {
  if (p.tipo === "flujo") return "Flujo de datos";
  if (p.tipo === "actividad") return "Actividad del registro";
  return TIPO_ELEMENTO[p.payload.tipo ?? ""] ?? "Elemento del mapa";
}

/** "Guía v1.0.0" a partir de "asistente_rat/1.0.0". */
export function versionGuia(promptVersion: string | null | undefined): string {
  const v = (promptVersion ?? "").split("/").pop();
  return v ? `Guía v${v}` : "";
}

/** La etiqueta que acompaña a toda propuesta: «Sugerido por IA · Modelo X · Guía vY». */
export function etiquetaIa(p: Pick<PropuestaApi, "ia">): string {
  if (p.ia.etiqueta) return p.ia.etiqueta;
  if (!p.ia.modelo || p.ia.modelo === "sin_ia") return "Sugerencia sin ayuda automática";
  return `Sugerido por IA · Modelo ${p.ia.modelo} · ${versionGuia(p.ia.prompt_version)}`;
}

export function tonoSeveridad(s: Severidad | string | null | undefined): string {
  if (s === "Crítica" || s === "Alta" || s === "Crítico" || s === "Alto") return "tone-alto";
  if (s === "Media" || s === "Medio") return "tone-medio";
  return "tone-bajo";
}

/** Diccionario código → nombre de los catálogos del mapa y del registro, para mostrar valores legibles. */
export type Diccionario = Record<string, Record<string, string>>;

export function diccionario(mapa: CatalogoMapa | null, rat: CatalogoRat | null): Diccionario {
  const d: Diccionario = {};
  const poner = (grupo: string, items: { codigo: string; nombre: string }[] | undefined) => {
    d[grupo] = { ...(d[grupo] ?? {}), ...Object.fromEntries((items ?? []).map((o) => [o.codigo, o.nombre])) };
  };
  if (mapa) {
    poner("tipo", mapa.tipos);
    poner("subtipo", Object.values(mapa.subtipos ?? {}).flat());
    poner("categorias_datos", mapa.categorias_datos);
    poner("categorias_titulares", mapa.categorias_titulares);
    poner("rol_tercero", mapa.roles_tercero);
    poner("garantia", mapa.garantias);
    poner("frecuencia", mapa.frecuencias);
    poner("medio", mapa.medios);
    poner("pais", mapa.paises);
  }
  if (rat) {
    poner("base_licitud", rat.bases_licitud);
    poner("base_sensibles", rat.bases_sensibles);
    poner("fuentes", rat.fuentes);
    poner("unidad", rat.unidades_plazo);
    poner("desde", rat.inicios_plazo);
    poner("medidas", rat.medidas_seguridad);
    poner("rol", rat.roles_empresa);
  }
  return d;
}

export function nombreDe(dic: Diccionario, grupo: string, codigo: string | null | undefined): string {
  if (!codigo) return "";
  return dic[grupo]?.[codigo] ?? codigo;
}

export function nombreRef(
  ref: string | null | undefined,
  refs: EstadoAsistente["referencias"],
  tipo: "elementos" | "flujos",
): string {
  if (!ref) return "Sin elegir";
  return refs[tipo][ref] ?? (ref.startsWith("nuevo:") ? "Propuesta por aceptar" : "Ya no está en el mapa");
}

export interface FilaPropuesta {
  campo: string;
  etiqueta: string;
  valor: string;
  explicacion?: string;
}

function lista(valores: string[] | undefined, dic: Diccionario, grupo: string): string {
  return (valores ?? []).map((v) => nombreDe(dic, grupo, v)).join(", ");
}

function plazoTexto(p: PlazoPropuesta, dic: Diccionario): string {
  const dato = nombreDe(dic, "categorias_datos", p.categoria);
  if (!p.plazo || !p.unidad) return `${dato}: sin plazo`;
  const desde = p.desde ? ` ${nombreDe(dic, "desde", p.desde)}` : "";
  return `${dato}: ${p.plazo} ${nombreDe(dic, "unidad", p.unidad)}${desde}`;
}

/** Lo que muestra la tarjeta de una propuesta: solo los campos con valor, con su explicación si la hay. */
export function filasPropuesta(
  p: Pick<PropuestaApi, "tipo" | "payload" | "payload_final" | "explicaciones">,
  dic: Diccionario,
  refs: EstadoAsistente["referencias"],
): FilaPropuesta[] {
  const d = p.payload_final ?? p.payload;
  const e = p.explicaciones ?? {};
  const filas: FilaPropuesta[] = [];
  const agregar = (campo: string, etiqueta: string, valor: string | null | undefined, explica = campo) => {
    if (valor) filas.push({ campo, etiqueta, valor, ...(e[explica] ? { explicacion: e[explica] } : {}) });
  };
  if (p.tipo === "elemento") {
    agregar("subtipo", "Tipo", nombreDe(dic, "subtipo", d.subtipo) || nombreDe(dic, "tipo", d.tipo), "tipo");
    agregar("proveedor", "Proveedor", d.proveedor);
    agregar("pais", "País donde están los datos", nombreDe(dic, "pais", d.pais) || "Sin informar");
    agregar("responsable", "Área responsable", d.responsable);
    agregar("categorias_datos", "Datos", lista(d.categorias_datos, dic, "categorias_datos"));
    agregar("categorias_titulares", "De quiénes", lista(d.categorias_titulares, dic, "categorias_titulares"));
    if (d.tipo === "tercero") {
      agregar("rol_tercero", "Rol del tercero", nombreDe(dic, "rol_tercero", d.rol_tercero));
      agregar("contrato_firmado", "Contrato de tratamiento",
        d.contrato_firmado === true ? "Sí" : d.contrato_firmado === false ? "No" : "Sin informar");
    }
  } else if (p.tipo === "flujo") {
    agregar("origen", "Desde", nombreRef(d.origen, refs, "elementos"));
    agregar("destino", "Hacia", nombreRef(d.destino, refs, "elementos"));
    agregar("categorias_datos", "Datos que viajan", lista(d.categorias_datos, dic, "categorias_datos"));
    agregar("garantia", "Garantía del envío", nombreDe(dic, "garantia", d.garantia));
    agregar("cifrado", "Cifrado", d.cifrado === true ? "Sí" : d.cifrado === false ? "No" : "");
  } else {
    agregar("area", "Área", d.area);
    agregar("finalidades", "Para qué", (d.finalidades ?? []).join(" · "));
    agregar("elementos", "Sistemas que usa", (d.elementos ?? []).map((r) => nombreRef(r, refs, "elementos")).join(", "));
    agregar("flujos", "Envíos de datos", (d.flujos ?? []).map((r) => nombreRef(r, refs, "flujos")).join(", "));
    agregar("base_licitud", "Base legal", nombreDe(dic, "base_licitud", d.base_licitud) || "Por elegir");
    agregar("base_sensibles", "Base para datos sensibles", nombreDe(dic, "base_sensibles", d.base_sensibles));
    agregar("plazos", "Cuánto tiempo se guardan", (d.plazos ?? []).map((x) => plazoTexto(x, dic)).join(" · "));
    agregar("medidas", "Medidas de seguridad", lista(d.medidas?.codigos, dic, "medidas"));
  }
  return filas;
}

/** Explicaciones que no quedaron junto a un campo visible (por ejemplo, la del riesgo o una general). */
export function explicacionesSueltas(p: Pick<PropuestaApi, "explicaciones">, filas: FilaPropuesta[]): [string, string][] {
  const usadas = new Set(filas.filter((f) => f.explicacion).map((f) => (f.campo === "subtipo" ? "tipo" : f.campo)));
  return Object.entries(p.explicaciones ?? {}).filter(([k]) => !usadas.has(k));
}

/** Propuestas de las que depende esta (sus "nuevo:<clave>") y que todavía no se aceptan. */
export function dependenciasPendientes(p: PropuestaApi, todas: PropuestaApi[]): PropuestaApi[] {
  const d = p.payload_final ?? p.payload;
  const refs = [d.origen, d.destino, ...(d.elementos ?? []), ...(d.flujos ?? [])].filter(
    (r): r is string => typeof r === "string" && r.startsWith("nuevo:"),
  );
  const claves = new Set(refs.map((r) => r.slice("nuevo:".length)));
  return todas.filter((x) => claves.has(x.clave) && x.estado === "sugerida");
}

/** Ordena para revisar: primero lo que no depende de nada (elementos), luego flujos y actividades. */
export function ordenarPropuestas(ps: PropuestaApi[]): PropuestaApi[] {
  const orden: Record<TipoPropuesta, number> = { elemento: 0, flujo: 1, actividad: 2 };
  return [...ps].sort((a, b) => orden[a.tipo] - orden[b.tipo] || a.id - b.id);
}

export function cuotaTexto(e: Pick<EstadoAsistente, "ia">): string {
  if (!e.ia.habilitada) return "Ayuda automática desactivada: puedes completar todo a mano.";
  const r = e.ia.cuota.respuestas;
  if (r.limite == null) return "Ayuda automática disponible.";
  if (!r.restantes) return "Usaste la ayuda automática de hoy. Puedes seguir a mano.";
  return `Te quedan ${r.restantes} de ${r.limite} respuestas con ayuda automática hoy.`;
}

export function validarRespuesta(texto: string, max: number): string | null {
  const t = texto.trim();
  if (!t) return "Escribe tu respuesta o usa «Saltar pregunta».";
  if (t.length > max) return `Tu respuesta supera los ${max} caracteres.`;
  return null;
}

export const EXTENSIONES_DOCUMENTO = [".pdf", ".docx", ".txt"] as const;
export const ACCEPT_DOCUMENTO =
  ".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain";

export function validarDocumento(archivo: Pick<File, "name" | "size"> | null, maxMb: number): string | null {
  if (!archivo) return "Elige el documento.";
  const nombre = archivo.name.toLowerCase();
  if (!EXTENSIONES_DOCUMENTO.some((x) => nombre.endsWith(x))) return "Sube un PDF, un Word (.docx) o un texto (.txt).";
  if (archivo.size === 0) return "El archivo está vacío.";
  if (archivo.size > maxMb * 1024 * 1024) return `El archivo pesa más de ${maxMb} MB.`;
  return null;
}

/** Los campos que cambió el usuario al editar (para enviar solo eso). */
export function cambios(original: PayloadPropuesta, editado: PayloadPropuesta): PayloadPropuesta {
  const salida: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(editado)) {
    if (JSON.stringify((original as Record<string, unknown>)[k] ?? null) !== JSON.stringify(v ?? null)) salida[k] = v;
  }
  return salida as PayloadPropuesta;
}

/* ------------------------------------------------------------ diseño de la pantalla */

/** Identidad visual de cada propuesta: define su color y su ícono. */
export type TipoVisual = "sistema" | "base_datos" | "tercero" | "flujo" | "actividad";

export function tipoVisual(p: Pick<PropuestaApi, "tipo" | "payload">): TipoVisual {
  if (p.tipo === "flujo" || p.tipo === "actividad") return p.tipo;
  const t = p.payload.tipo;
  return t === "base_datos" || t === "tercero" ? t : "sistema";
}

/** Cuántas preguntas van respondidas (o saltadas) de todo el banco. */
export function progresoEntrevista(sesion: Pick<SesionApi, "areas" | "area_actual" | "paso" | "terminada">): {
  hechas: number; total: number;
} {
  const total = sesion.areas.reduce((n, a) => n + a.preguntas, 0);
  if (sesion.terminada) return { hechas: total, total };
  const hechas = sesion.areas.reduce((n, a) => {
    if (a.codigo === sesion.area_actual) return n + Math.min(sesion.paso, a.preguntas);
    return n + (a.completada ? a.preguntas : 0);
  }, 0);
  return { hechas, total };
}

export interface GrupoPropuestas {
  tipo: TipoPropuesta;
  titulo: string;
  propuestas: PropuestaApi[];
}

/** Propuestas agrupadas en el orden en que conviene revisarlas (sin grupos vacíos). */
export function agruparPropuestas(ps: PropuestaApi[]): GrupoPropuestas[] {
  const titulos: Record<TipoPropuesta, string> = {
    elemento: "Sistemas, bases de datos y terceros",
    flujo: "Flujos de datos",
    actividad: "Actividades del registro",
  };
  return (["elemento", "flujo", "actividad"] as TipoPropuesta[])
    .map((tipo) => ({ tipo, titulo: titulos[tipo], propuestas: ordenarPropuestas(ps.filter((p) => p.tipo === tipo)) }))
    .filter((g) => g.propuestas.length > 0);
}

/** «1 sistema», «2 flujos», «3 actividades»: plural en español para los contadores. */
export function cantidad(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`;
}

export const NIVEL_CONFIANZA: Record<PropuestaApi["confianza"], { segmentos: 1 | 2 | 3; texto: string }> = {
  alta: { segmentos: 3, texto: "Confianza alta" },
  media: { segmentos: 2, texto: "Confianza media" },
  baja: { segmentos: 1, texto: "Confianza baja: revísala con cuidado" },
};
