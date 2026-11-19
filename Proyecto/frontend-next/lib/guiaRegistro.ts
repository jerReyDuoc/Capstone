/**
 * Asistente de registro como guía (navegador → /bff/cliente/api/asistente/guia).
 *
 * Vive dentro de las vistas del mapa de datos y del registro de actividades, como el tutor IA: un panel
 * lateral con respuestas cortas que orientan. No arma ni propone registros: la persona completa todo a
 * mano. La conversación la guarda el navegador (sessionStorage) y se envía en cada pregunta.
 *
 * Corrección 18-11: la conversación es de UNA cuenta. Se guarda bajo `guia-registro:conversacion:<usuarioId>`
 * (antes era una clave fija y la cuenta que entraba después en la misma pestaña veía la conversación de la
 * anterior) y se borra al cerrar o iniciar sesión (lib/sesionNavegador.ts). Sin usuario conocido no se lee ni
 * se guarda nada.
 *
 * Aquí solo hay llamadas y lógica de presentación pura (probada en tests/guia_registro.test.ts).
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";

export const BASE_GUIA = "/bff/cliente/api/asistente/guia";
export const MAX_CARACTERES_GUIA = 2000;
export const MAX_MENSAJES_GUARDADOS = 30;
export const TURNOS_ENVIADOS = 6;
/** Prefijo de todo lo que la guía guarda en el navegador (lo borra limpiarDatosDeCuenta al cerrar sesión). */
export const PREFIJO_ALMACEN_GUIA = "guia-registro:";
/** Clave de antes de la corrección 18-11 (sin dueño): se descarta si aparece. */
const CLAVE_SIN_DUENO = `${PREFIJO_ALMACEN_GUIA}conversacion`;
export const claveConversacion = (usuarioId: number) => `${CLAVE_SIN_DUENO}:${usuarioId}`;

export type VistaGuia = "mapa" | "registro";
export type Severidad = "Crítica" | "Alta" | "Media" | "Baja";
export type CodigoAlerta = "sensible_sin_base" | "transferencia_sin_garantia" | "actividad_sin_plazo" | "flujo_sin_actividad";

export interface AlertaRegistro {
  codigo: CodigoAlerta;
  severidad: Severidad;
  texto: string;
  referencia: { tipo: "flujo" | "actividad" | "propuesta"; id?: number } | null;
}

export interface CuotaGuia {
  usados: number;
  limite: number | null;
  restantes: number | null;
}

export interface ResumenGuia {
  revision: AlertaRegistro[];
  mapa: { elementos: number; flujos: number; actividades: number };
  ia: { habilitada: boolean; cuota: CuotaGuia; reinicia_en: string };
  limites: { max_caracteres: number };
  sugerencias: Record<VistaGuia, string[]>;
}

export interface RespuestaGuia {
  respuesta: string;
  sugerencias: string[];
  bloqueado: boolean;
  sin_ia: string | null;
  cuota: CuotaGuia;
}

export interface MensajeGuia {
  id: string;
  rol: "usuario" | "guia";
  texto: string;
  sugerencias?: string[];
  bloqueado?: boolean;
}

/* ------------------------------------------------------------ llamadas */

export const cargarResumenGuia = () => pedir<ResumenGuia>(BASE_GUIA);

/** Nunca se reintenta: llama al servicio de IA y gasta cuota. */
export const preguntarGuia = (texto: string, vista: VistaGuia, historial: MensajeGuia[]) =>
  pedir<RespuestaGuia>(BASE_GUIA, {
    method: "POST",
    json: { texto, vista, historial: historialParaEnviar(historial) },
  }, { reintentos: 0 });

/* ------------------------------------------------------------ conversación */

/** Los últimos turnos (sin los bloqueados), recortados: es lo que el modelo ve de la conversación. */
export function historialParaEnviar(mensajes: MensajeGuia[], max = TURNOS_ENVIADOS): { rol: "usuario" | "guia"; texto: string }[] {
  return mensajes
    .filter((m) => !m.bloqueado && m.texto.trim())
    .slice(-max)
    .map((m) => ({ rol: m.rol, texto: m.texto.slice(0, 600) }));
}

export function leerConversacion(
  almacen: Pick<Storage, "getItem" | "removeItem"> | null,
  usuarioId: number | null,
): MensajeGuia[] {
  if (usuarioId == null) return [];
  try {
    almacen?.removeItem(CLAVE_SIN_DUENO); // la de antes no sabe de quién es: nunca se muestra
    const crudo = almacen?.getItem(claveConversacion(usuarioId));
    const lista = crudo ? (JSON.parse(crudo) as unknown) : [];
    if (!Array.isArray(lista)) return [];
    return lista
      .filter((m): m is MensajeGuia =>
        !!m && typeof m === "object" && typeof (m as MensajeGuia).texto === "string"
        && ((m as MensajeGuia).rol === "usuario" || (m as MensajeGuia).rol === "guia"))
      .slice(-MAX_MENSAJES_GUARDADOS);
  } catch {
    return [];
  }
}

export function guardarConversacion(
  almacen: Pick<Storage, "setItem" | "removeItem"> | null,
  usuarioId: number | null,
  mensajes: MensajeGuia[],
) {
  if (usuarioId == null) return;
  const clave = claveConversacion(usuarioId);
  try {
    if (!mensajes.length) almacen?.removeItem(clave);
    else almacen?.setItem(clave, JSON.stringify(mensajes.slice(-MAX_MENSAJES_GUARDADOS)));
  } catch {
    /* sin almacenamiento (modo privado): la conversación dura lo que dure la página */
  }
}

let contador = 0;
export const nuevoId = () => `${Date.now().toString(36)}-${(contador++).toString(36)}`;

export type ValidacionPregunta = { ok: true; texto: string } | { ok: false; motivo: string };

export function validarPregunta(texto: string, max = MAX_CARACTERES_GUIA): ValidacionPregunta {
  const limpio = texto.trim();
  if (!limpio) return { ok: false, motivo: "Escribe tu pregunta." };
  if (limpio.length > max) return { ok: false, motivo: `Tu pregunta supera los ${max} caracteres.` };
  return { ok: true, texto: limpio };
}

/** Párrafos del texto (sin HTML: React escapa el contenido). */
export const parrafos = (texto: string) =>
  texto.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);

export function cuotaTexto(c: CuotaGuia | null | undefined, habilitada = true): string {
  if (!habilitada) return "Ayuda automática desactivada: te doy la guía básica.";
  if (!c || c.limite == null || c.restantes == null) return "";
  if (c.restantes === 0) return "Usaste las preguntas de hoy. Mañana se renuevan.";
  return `Te ${c.restantes === 1 ? "queda 1 pregunta" : `quedan ${c.restantes} preguntas`} hoy.`;
}

/** Mensaje para la persona según el código de error del backend o del BFF. */
export function mensajeGuia(e: unknown): string {
  const info = e instanceof ErrorBff ? e.info : null;
  switch (info?.codigo) {
    case "CONTRATO_NO_VIGENTE":
      return "El servicio de tu empresa no está activo. Contacta a Therion Labs para renovarlo.";
    case "SESION_EXPIRADA":
      return "Tu sesión terminó. Vuelve a ingresar para seguir.";
    case "ASISTENTE_RAFAGA":
      return info.mensaje || "Estás preguntando muy rápido. Espera unos segundos.";
    case "AYUDA_NO_DISPONIBLE":
    case "LIMITADOR_NO_DISPONIBLE":
      return "La guía no pudo responder ahora. Tu pregunta no se perdió: vuelve a enviarla en unos segundos.";
    case "SIN_CONEXION":
      return "No pudimos conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.";
    default:
      return info?.mensaje || "No pudimos completar la acción. Inténtalo de nuevo.";
  }
}

/* ------------------------------------------------------------ revisión de mi registro (simple) */

/** Qué significa cada alerta y qué hacer, en una frase; y a qué vista lleva resolverla. */
export const TIPO_ALERTA: Record<CodigoAlerta, { titulo: string; queHacer: string; vista: VistaGuia }> = {
  sensible_sin_base: {
    titulo: "Datos sensibles sin base legal",
    queHacer: "Abre la actividad y, en el paso de base legal, elige la base para datos sensibles.",
    vista: "registro",
  },
  transferencia_sin_garantia: {
    titulo: "Envíos fuera de Chile sin garantía",
    queHacer: "Edita el flujo en el mapa y elige la garantía del envío (por ejemplo, cláusulas contractuales).",
    vista: "mapa",
  },
  actividad_sin_plazo: {
    titulo: "Falta cuánto tiempo se guardan los datos",
    queHacer: "Abre la actividad y completa el paso de plazos.",
    vista: "registro",
  },
  flujo_sin_actividad: {
    titulo: "Envíos de datos sin actividad",
    queHacer: "Crea la actividad del registro que usa ese envío, o agrégalo a una que ya tengas.",
    vista: "registro",
  },
};

const ORDEN_SEVERIDAD: Record<Severidad, number> = { "Crítica": 0, Alta: 1, Media: 2, Baja: 3 };

export interface GrupoRevision {
  codigo: CodigoAlerta;
  titulo: string;
  queHacer: string;
  vista: VistaGuia;
  severidad: Severidad;
  items: AlertaRegistro[];
}

/** Las alertas agrupadas por tipo (una tarjeta por problema), lo más grave primero. */
export function agruparRevision(alertas: AlertaRegistro[]): GrupoRevision[] {
  const grupos = new Map<CodigoAlerta, GrupoRevision>();
  for (const a of alertas) {
    const tipo = TIPO_ALERTA[a.codigo];
    if (!tipo) continue;
    const g = grupos.get(a.codigo) ?? { codigo: a.codigo, ...tipo, severidad: a.severidad, items: [] };
    g.items.push(a);
    if (ORDEN_SEVERIDAD[a.severidad] < ORDEN_SEVERIDAD[g.severidad]) g.severidad = a.severidad;
    grupos.set(a.codigo, g);
  }
  return [...grupos.values()].sort((x, y) => ORDEN_SEVERIDAD[x.severidad] - ORDEN_SEVERIDAD[y.severidad]);
}

export interface PasoSiguiente {
  id: "mapa" | "flujos" | "actividades" | "alertas" | "listo";
  titulo: string;
  texto: string;
  vista: VistaGuia;
}

/** El único paso que conviene hacer ahora, según lo que ya tiene el registro. */
export function pasoSiguiente(r: Pick<ResumenGuia, "mapa" | "revision">): PasoSiguiente {
  const { elementos, flujos, actividades } = r.mapa;
  if (elementos === 0) {
    return { id: "mapa", vista: "mapa", titulo: "Agrega tu primer sistema",
      texto: "En el mapa de datos, usa «Agregar elemento» para el sistema que más usas (por ejemplo, el de remuneraciones)." };
  }
  if (flujos === 0 && elementos >= 2) {
    return { id: "flujos", vista: "mapa", titulo: "Une tus sistemas con flujos",
      texto: "Con «Agregar flujo» indica qué datos se envían de un sistema o proveedor a otro." };
  }
  if (actividades === 0) {
    return { id: "actividades", vista: "registro", titulo: "Crea tu primera actividad",
      texto: "En el registro de actividades, usa «Nueva actividad» para algo que hace tu empresa con datos (por ejemplo, pagar sueldos)." };
  }
  if (r.revision.length) {
    return { id: "alertas", vista: r.revision.some((a) => TIPO_ALERTA[a.codigo]?.vista === "registro") ? "registro" : "mapa",
      titulo: "Resuelve los puntos pendientes", texto: "Abajo te dejamos cada punto con lo que hay que hacer." };
  }
  return { id: "listo", vista: "registro", titulo: "Tu registro está al día",
    texto: "No encontramos puntos por resolver. Cuando quieras, descarga los informes o haz la revisión interna." };
}

/** La pregunta que se envía al pulsar «¿Cómo lo resuelvo?» en un punto de la revisión. */
export const preguntaAlerta = (g: Pick<GrupoRevision, "titulo">) =>
  `¿Cómo resuelvo este punto de mi registro: «${g.titulo}»?`;

export const cantidad = (n: number, singular: string, plural: string) => `${n} ${n === 1 ? singular : plural}`;
