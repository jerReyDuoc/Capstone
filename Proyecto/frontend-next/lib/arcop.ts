/**
 * HU-32 · Derechos ARCOP en la página web: textos, reglas y llamadas (lógica pura + fetch).
 *
 * Tres puertas a la misma API (/api/arcop en FastAPI), cada una por su BFF:
 *   - usuario temporal (encuestado, entra con N.º de evaluación + clave): /bff/api
 *   - usuario definitivo (cliente, entra con su cuenta):                   /bff/cliente/api
 *   - administrador (panel interno):                                       /bff/admin/api
 *
 * El backend decide todo (dueño, transiciones, plazos). Aquí solo se traduce a lenguaje
 * claro y se anticipa qué botones mostrar, para no ofrecer acciones que el backend rechazaría.
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import { fechaChile, fechaDelServidor } from "@/lib/fechas";

/* ------------------------------------------------------------------ tipos */
export const TIPOS_ARCOP = ["acceso", "rectificacion", "supresion", "oposicion", "portabilidad", "bloqueo"] as const;
export type TipoArcop = (typeof TIPOS_ARCOP)[number];

export const ESTADOS_ARCOP = [
  "recibida", "en_revision", "pendiente_informacion", "en_proceso", "resuelta", "rechazada", "cancelada",
] as const;
export type EstadoArcop = (typeof ESTADOS_ARCOP)[number];
export const ESTADOS_FINALES: ReadonlySet<EstadoArcop> = new Set(["resuelta", "rechazada", "cancelada"]);

export type PerfilTitular = "encuestado" | "cliente";
export type FormatoExportacion = "json" | "csv";

export interface SolicitudArcop {
  id_solicitud: number;
  codigo_seguimiento: string;
  tipo: TipoArcop;
  estado: EstadoArcop;
  usuario_temporal_id: number | null;
  evaluacion_id: number | null;
  usuario_definitivo_id: number | null;
  fecha_creacion: string;
  fecha_actualizacion: string | null;
  fecha_cierre: string | null;
  fecha_limite_respuesta: string | null;
  fecha_limite_informacion: string | null;
  plazo_vencido: boolean;
  fecha_prorroga: string | null;
}

export interface EventoArcop {
  id_evento: number;
  fecha: string;
  tipo_evento: string;
  estado_anterior: string | null;
  estado_nuevo: string | null;
  actor_rol: string;
  actor_id: number | null;
  comentario: string | null;
}

export interface DetalleArcop extends SolicitudArcop {
  descripcion: string;
  respuesta: string | null;
  transiciones_posibles: EstadoArcop[];
  historial: EventoArcop[];
}

export interface PaginaArcop {
  items: SolicitudArcop[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface SeguimientoArcop {
  codigo_seguimiento: string;
  tipo: TipoArcop;
  estado: EstadoArcop;
  fecha_creacion: string;
  fecha_actualizacion: string | null;
  fecha_limite_respuesta: string | null;
  fecha_cierre: string | null;
  prorrogada: boolean;
  plazo_vencido: boolean;
}

export interface CatalogoArcop {
  plazo_respuesta_dias: number | null;
  plazo_prorroga_dias: number | null;
  plazo_bloqueo_dias_habiles: number | null;
  plazo_informacion_dias: number | null;
}

/* ------------------------------------------------------------------ límites (iguales al backend) */
export const DESCRIPCION_MIN = 10;
export const DESCRIPCION_MAX = 5000;
export const COMENTARIO_MAX = 2000;
export const RESPUESTA_MIN = 10;
export const RESPUESTA_MAX = 10000;
export const MOTIVO_PRORROGA_MIN = 10;

/** Mensaje de error de un texto obligatorio (o null si está bien). */
export function errorTexto(texto: string, min: number, max: number, campo = "El texto"): string | null {
  const largo = texto.trim().length;
  if (!largo) return `${campo} es obligatorio.`;
  if (largo < min) return `${campo} debe tener al menos ${min} caracteres (faltan ${min - largo}).`;
  if (largo > max) return `${campo} no puede superar ${max.toLocaleString("es-CL")} caracteres.`;
  return null;
}

/* ------------------------------------------------------------------ textos de cada derecho */
export interface InfoDerecho {
  /** Lo que el titular quiere hacer, en sus palabras. */
  accion: string;
  /** Nombre legal del derecho. */
  nombre: string;
  descripcion: string;
  /** Qué escribir en la descripción. */
  guia: string;
  ejemplo: string;
  icono: "buscar" | "documento" | "basura" | "alerta" | "descargar" | "candado";
}

export const DERECHOS: Record<TipoArcop, InfoDerecho> = {
  acceso: {
    accion: "Ver qué datos tienen de mí",
    nombre: "Acceso",
    descripcion: "Conoce qué datos personales tuyos guarda la plataforma y para qué se usan. Cuando se resuelva, podrás descargarlos.",
    guia: "Cuéntanos qué quieres saber: todos tus datos o algo en particular.",
    ejemplo: "Quiero saber todos los datos personales que guardan de mí y para qué los usan.",
    icono: "buscar",
  },
  rectificacion: {
    accion: "Corregir un dato",
    nombre: "Rectificación",
    descripcion: "Pide que corrijamos un dato tuyo que esté incorrecto, incompleto o desactualizado.",
    guia: "Indica qué dato está mal y cuál es el valor correcto.",
    ejemplo: "Mi correo registrado está mal escrito. El correcto es…",
    icono: "documento",
  },
  supresion: {
    accion: "Eliminar mis datos",
    nombre: "Supresión",
    descripcion: "Pide que borremos tus datos personales. Es definitivo y no se puede deshacer.",
    guia: "Si quieres, cuéntanos el motivo. No es obligatorio dar razones.",
    ejemplo: "Quiero que eliminen todos mis datos personales de la plataforma.",
    icono: "basura",
  },
  oposicion: {
    accion: "Oponerme a un uso de mis datos",
    nombre: "Oposición",
    descripcion: "Pide que dejemos de usar tus datos para un fin específico, aunque se sigan guardando.",
    guia: "Indica a qué uso te opones y, si quieres, por qué.",
    ejemplo: "No quiero que mis respuestas se usen en la comparación con mi rubro.",
    icono: "alerta",
  },
  portabilidad: {
    accion: "Llevarme mis datos",
    nombre: "Portabilidad",
    descripcion: "Recibe tus datos en un archivo estructurado (JSON o CSV) para traspasarlos a otro servicio.",
    guia: "Cuéntanos qué datos quieres llevarte. Cuando se resuelva, podrás descargarlos aquí mismo.",
    ejemplo: "Quiero una copia de mis respuestas y evidencias para llevarlas a otro proveedor.",
    icono: "descargar",
  },
  bloqueo: {
    accion: "Bloquear temporalmente mis datos",
    nombre: "Bloqueo temporal",
    descripcion: "Pide que suspendamos el uso de tus datos mientras se revisa otra solicitud o un reclamo tuyo.",
    guia: "Indica por qué necesitas el bloqueo y, si corresponde, a qué solicitud se refiere.",
    ejemplo: "Mientras revisan mi solicitud de rectificación, no quiero que se usen mis datos.",
    icono: "candado",
  },
};

/** Lo que pasa al aprobar una supresión, según quién la pide (lo hace el backend). */
export const EFECTO_SUPRESION: Record<PerfilTitular, string> = {
  encuestado:
    "Se borrarán tu correo, tus justificaciones y tus evidencias, y tu clave dejará de funcionar. Solo se conservan los puntajes, sin ningún vínculo contigo. Podrás seguir el estado con tu código de seguimiento.",
  cliente:
    "Se borrarán tu nombre, tu correo y tus textos, y tu cuenta se cerrará. Los datos de tu empresa (evaluaciones y documentos) no se tocan, porque pertenecen a la empresa contratante. Podrás seguir el estado con tu código de seguimiento.",
};

export const exportable = (tipo: TipoArcop) => tipo === "acceso" || tipo === "portabilidad";

/* ------------------------------------------------------------------ estados */
export type Tono = "info" | "medio" | "ok" | "alto" | "naranja";

export const ESTADOS: Record<EstadoArcop, { etiqueta: string; tono: Tono; titular: string; admin: string }> = {
  recibida: {
    etiqueta: "Recibida", tono: "info",
    titular: "La recibimos. Un responsable la revisará pronto.",
    admin: "Nueva: revísala y pásala a revisión.",
  },
  en_revision: {
    etiqueta: "En revisión", tono: "info",
    titular: "Un responsable está revisando tu solicitud.",
    admin: "Verifica la solicitud: pide información si falta algo o pásala a proceso.",
  },
  pendiente_informacion: {
    etiqueta: "Necesita tu respuesta", tono: "medio",
    titular: "Necesitamos un antecedente tuyo para continuar. Respóndelo abajo.",
    admin: "Esperando que el titular aporte la información pedida.",
  },
  en_proceso: {
    etiqueta: "En proceso", tono: "info",
    titular: "Estamos aplicando lo que pediste.",
    admin: "Aplica lo solicitado y registra la respuesta.",
  },
  resuelta: {
    etiqueta: "Resuelta", tono: "ok",
    titular: "Tu solicitud fue atendida. Revisa la respuesta.",
    admin: "Cerrada: se atendió lo solicitado.",
  },
  rechazada: {
    etiqueta: "Rechazada", tono: "alto",
    titular: "No pudimos acoger tu solicitud. Revisa el motivo en la respuesta.",
    admin: "Cerrada: no se acogió.",
  },
  cancelada: {
    etiqueta: "Cancelada", tono: "naranja",
    titular: "Cancelaste esta solicitud.",
    admin: "Cerrada: el titular desistió.",
  },
};

export const esFinal = (estado: EstadoArcop) => ESTADOS_FINALES.has(estado);

/** Los 4 hitos que ve el titular: Enviada → En revisión → En proceso → Respondida. */
export const PASOS = ["Enviada", "En revisión", "En proceso", "Respondida"] as const;

export function pasoActual(estado: EstadoArcop): number {
  switch (estado) {
    case "recibida":
      return 0;
    case "en_revision":
    case "pendiente_informacion":
      return 1;
    case "en_proceso":
      return 2;
    default:
      return 3;
  }
}

/* ------------------------------------------------------------------ plazos */
const DIA_MS = 86_400_000;

/** Días enteros (hora de Chile no importa: es una cuenta de días calendario aproximada). */
export function diasHasta(iso: string | null | undefined, ahora = new Date()): number | null {
  const d = fechaDelServidor(iso);
  if (!d) return null;
  return Math.ceil((d.getTime() - ahora.getTime()) / DIA_MS);
}

export interface TextoPlazo {
  texto: string;
  tono: Tono;
}

/** "Responderemos antes del 10 dic 2026 (en 12 días)" / "Plazo vencido hace 2 días" / "Cerrada el …". */
export function textoPlazo(s: SolicitudArcop, ahora = new Date()): TextoPlazo | null {
  if (esFinal(s.estado)) return s.fecha_cierre ? { texto: `Cerrada el ${fechaChile(s.fecha_cierre)}`, tono: "info" } : null;
  if (!s.fecha_limite_respuesta) return null;
  const dias = diasHasta(s.fecha_limite_respuesta, ahora) ?? 0;
  const fecha = fechaChile(s.fecha_limite_respuesta);
  if (s.plazo_vencido || dias < 0) {
    const n = Math.abs(dias);
    return { texto: `Plazo vencido${n ? ` hace ${n} ${n === 1 ? "día" : "días"}` : " hoy"} (${fecha})`, tono: "alto" };
  }
  const cuando = dias === 0 ? "hoy" : dias === 1 ? "mañana" : `en ${dias} días`;
  return { texto: `Plazo de respuesta: ${fecha} (${cuando})`, tono: dias <= 5 ? "medio" : "info" };
}

/* ------------------------------------------------------------------ acciones posibles */
export interface AccionesTitular {
  cancelar: boolean;
  aportar: boolean;
  descargar: boolean;
}

export function accionesTitular(d: DetalleArcop): AccionesTitular {
  return {
    cancelar: d.transiciones_posibles.includes("cancelada"),
    aportar: d.estado === "pendiente_informacion",
    descargar: d.estado === "resuelta" && exportable(d.tipo),
  };
}

export type AccionAdmin = "en_revision" | "pendiente_informacion" | "en_proceso" | "resolver" | "rechazar" | "prorrogar";

/** Qué puede hacer el admin ahora, en el orden en que se muestran. */
export function accionesAdmin(d: DetalleArcop, ahora = new Date()): AccionAdmin[] {
  const t = new Set(d.transiciones_posibles);
  const lista: AccionAdmin[] = [];
  if (t.has("en_revision")) lista.push("en_revision");
  if (t.has("pendiente_informacion")) lista.push("pendiente_informacion");
  if (t.has("en_proceso")) lista.push("en_proceso");
  if (t.has("resuelta")) lista.push("resolver");
  if (t.has("rechazada")) lista.push("rechazar");
  if (puedeProrrogar(d, ahora)) lista.push("prorrogar");
  return lista;
}

export function puedeProrrogar(s: SolicitudArcop, ahora = new Date()): boolean {
  if (esFinal(s.estado) || s.tipo === "bloqueo" || s.fecha_prorroga) return false;
  const limite = fechaDelServidor(s.fecha_limite_respuesta);
  return Boolean(limite && limite.getTime() >= ahora.getTime());
}

/** El siguiente paso "natural" del admin (botón principal). */
export function siguientePasoAdmin(d: DetalleArcop): AccionAdmin | null {
  switch (d.estado) {
    case "recibida":
      return "en_revision";
    case "en_revision":
      return "en_proceso";
    case "en_proceso":
      return "resolver";
    default:
      return null;
  }
}

/** Indicaciones para el admin según el derecho (la rectificación se corrige a mano). */
export const GUIA_ADMIN: Record<TipoArcop, string> = {
  acceso:
    "Al resolverla, el titular podrá descargar sus datos (JSON o CSV) desde su página. En la respuesta explica para qué se usan sus datos.",
  rectificacion:
    "Corrige a mano el dato indicado (por ejemplo, en Empresas cliente o en la base de datos) y luego resuelve contando qué se corrigió, sin repetir el dato personal.",
  supresion:
    "Al resolverla se anonimizan de forma IRREVERSIBLE los datos del titular y pierde el acceso. Se conservan solo puntajes sin vínculo personal.",
  oposicion:
    "Evalúa si corresponde dejar de usar los datos para el fin indicado. Registra en la respuesta qué se hizo.",
  portabilidad:
    "Al resolverla, el titular podrá descargar sus datos en formato estructurado (JSON o CSV) desde su página.",
  bloqueo:
    "Se responde en 2 días hábiles y no admite prórroga. Suspende el uso de los datos mientras se revisa el caso.",
};

/** Quién es el titular, en una frase para el admin. */
export function titularDe(s: SolicitudArcop): string {
  if (s.usuario_definitivo_id != null) return `Usuario de empresa cliente (id ${s.usuario_definitivo_id})`;
  if (s.evaluacion_id != null) return `Autodiagnóstico sin cuenta · evaluación N.º ${s.evaluacion_id}`;
  return `Invitado (usuario temporal ${s.usuario_temporal_id ?? "—"})`;
}

/* ------------------------------------------------------------------ historial */
/** Frase de un evento del historial. `paraTitular` habla en segunda persona. */
export function textoEvento(e: EventoArcop, paraTitular: boolean): string {
  const deTitular = e.actor_rol !== "admin_therion";
  const nuevo = (e.estado_nuevo ?? "") as EstadoArcop;
  switch (e.tipo_evento) {
    case "creada":
      return paraTitular ? "Enviaste la solicitud" : "El titular envió la solicitud";
    case "cambio_estado":
      if (nuevo === "pendiente_informacion") return paraTitular ? "Te pidieron más información" : "Se pidió información al titular";
      return `${paraTitular ? "El responsable la pasó" : "Pasó"} a «${ESTADOS[nuevo]?.etiqueta ?? nuevo}»`;
    case "informacion_aportada":
      return paraTitular ? "Enviaste la información pedida" : "El titular aportó la información";
    case "prorroga":
      return "Se prorrogó el plazo de respuesta";
    case "resolucion":
      return nuevo === "resuelta" ? "Solicitud resuelta" : "Solicitud rechazada";
    case "cancelacion":
      return deTitular && paraTitular ? "Cancelaste la solicitud" : "El titular canceló la solicitud";
    case "anonimizacion":
      return "Se anonimizaron los datos personales";
    default:
      return e.tipo_evento;
  }
}

/* ------------------------------------------------------------------ código de seguimiento */
const ALFABETO = /[0-9A-HJKMNP-TV-Z]/;

/** Igual que el backend: minúsculas, espacios, sin guiones y O/0, I/L/1. "" si no tiene 8 caracteres. */
export function normalizarCodigo(codigo: string): string {
  let limpio = (codigo ?? "").toUpperCase().replace(/[^0-9A-Z]/g, "").replace(/O/g, "0").replace(/[IL]/g, "1");
  if (limpio.startsWith("ARC")) limpio = limpio.slice(3);
  if (limpio.length !== 8 || ![...limpio].every((c) => ALFABETO.test(c))) return "";
  return `ARC-${limpio.slice(0, 4)}-${limpio.slice(4)}`;
}

/* ------------------------------------------------------------------ errores */
export function mensajeError(e: unknown, porDefecto = "No pudimos completar la acción. Inténtalo de nuevo."): string {
  if (!(e instanceof ErrorBff)) return porDefecto;
  const { codigo, mensaje } = e.info;
  switch (codigo) {
    case "SESION_EXPIRADA":
      return "Tu sesión terminó. Vuelve a ingresar para continuar.";
    case "SIN_CONEXION":
      return "No pudimos conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.";
    case "DEMASIADOS_INTENTOS":
      return "Demasiados intentos seguidos. Espera un momento y vuelve a intentarlo.";
    case "TRANSICION_INVALIDA":
      return "La solicitud cambió mientras la mirabas. Actualiza para ver su estado actual.";
    case "EXPORTACION_NO_DISPONIBLE":
      return mensaje || "La descarga estará disponible cuando la solicitud esté resuelta.";
    default:
      return mensaje || porDefecto;
  }
}

/* ------------------------------------------------------------------ llamadas del titular */
export const BASE_TITULAR: Record<PerfilTitular, string> = {
  encuestado: "/bff/api",
  cliente: "/bff/cliente/api",
};

export function nombreDesdeDisposicion(disposicion: string | null, porDefecto: string): string {
  const m = /filename="([\w.-]+)"/.exec(disposicion ?? "");
  return m ? m[1] : porDefecto;
}

export function apiTitular(perfil: PerfilTitular) {
  const base = `${BASE_TITULAR[perfil]}/arcop`;
  return {
    catalogo: () => pedir<CatalogoArcop>(`${base}/catalogo`),
    listar: () => pedir<PaginaArcop>(`${base}/solicitudes?size=100`),
    detalle: (id: number) => pedir<DetalleArcop>(`${base}/solicitudes/${id}`),
    crear: (tipo: TipoArcop, descripcion: string) =>
      pedir<DetalleArcop>(`${base}/solicitudes`, { method: "POST", json: { tipo, descripcion: descripcion.trim() } }),
    cancelar: (id: number, motivo?: string) =>
      pedir<DetalleArcop>(`${base}/solicitudes/${id}/cancelacion`, {
        method: "POST", json: motivo?.trim() ? { motivo: motivo.trim() } : {},
      }),
    aportar: (id: number, informacion: string) =>
      pedir<DetalleArcop>(`${base}/solicitudes/${id}/informacion`, { method: "POST", json: { informacion: informacion.trim() } }),
    async descargar(id: number, formato: FormatoExportacion): Promise<{ blob: Blob; nombre: string }> {
      const res = await fetch(`${base}/solicitudes/${id}/exportacion?formato=${formato}`, {
        credentials: "same-origin", cache: "no-store",
      });
      if (!res.ok) {
        let info = { codigo: `HTTP_${res.status}`, mensaje: "" };
        try {
          info = ((await res.json()) as { error: typeof info }).error ?? info;
        } catch {
          /* sin cuerpo */
        }
        throw new ErrorBff(res.status, info);
      }
      return { blob: await res.blob(), nombre: nombreDesdeDisposicion(res.headers.get("content-disposition"), `mis-datos.${formato}`) };
    },
  };
}

/* ------------------------------------------------------------------ llamadas del admin */
export interface FiltrosAdmin {
  estado: EstadoArcop | null;
  tipo: TipoArcop | null;
  vencidas: boolean;
  evaluacion_id: number | null;
  page: number;
}

export const FILTROS_ADMIN_INICIALES: FiltrosAdmin = { estado: null, tipo: null, vencidas: false, evaluacion_id: null, page: 1 };
export const TAMANO_PAGINA_ADMIN = 20;

export function queryAdmin(f: FiltrosAdmin, size = TAMANO_PAGINA_ADMIN): string {
  const q = new URLSearchParams({ page: String(f.page), size: String(size) });
  if (f.estado) q.set("estado", f.estado);
  if (f.tipo) q.set("tipo", f.tipo);
  if (f.vencidas) q.set("vencidas", "true");
  if (f.evaluacion_id) q.set("evaluacion_id", String(f.evaluacion_id));
  return q.toString();
}

const BASE_ADMIN = "/bff/admin/api/arcop";

export const apiAdminArcop = {
  catalogo: () => pedir<CatalogoArcop>(`${BASE_ADMIN}/catalogo`),
  listar: (f: FiltrosAdmin) => pedir<PaginaArcop>(`${BASE_ADMIN}/solicitudes?${queryAdmin(f)}`),
  /** Totales para la franja de arriba (una consulta mínima por cifra). */
  async conteos(): Promise<Record<"recibida" | "en_revision" | "pendiente_informacion" | "en_proceso" | "vencidas", number>> {
    const total = (q: string) => pedir<PaginaArcop>(`${BASE_ADMIN}/solicitudes?page=1&size=1&${q}`).then((p) => p.total);
    const [recibida, en_revision, pendiente_informacion, en_proceso, vencidas] = await Promise.all([
      total("estado=recibida"), total("estado=en_revision"), total("estado=pendiente_informacion"),
      total("estado=en_proceso"), total("vencidas=true"),
    ]);
    return { recibida, en_revision, pendiente_informacion, en_proceso, vencidas };
  },
  detalle: (id: number) => pedir<DetalleArcop>(`${BASE_ADMIN}/solicitudes/${id}`),
  cambiarEstado: (id: number, estado: "en_revision" | "pendiente_informacion" | "en_proceso", comentario?: string) =>
    pedir<DetalleArcop>(`${BASE_ADMIN}/solicitudes/${id}/estado`, {
      method: "PATCH", json: { estado, ...(comentario?.trim() ? { comentario: comentario.trim() } : {}) },
    }),
  prorrogar: (id: number, motivo: string) =>
    pedir<DetalleArcop>(`${BASE_ADMIN}/solicitudes/${id}/prorroga`, { method: "POST", json: { motivo: motivo.trim() } }),
  resolver: (id: number, resultado: "resuelta" | "rechazada", respuesta: string) =>
    pedir<DetalleArcop>(`${BASE_ADMIN}/solicitudes/${id}/resolucion`, {
      method: "POST", json: { resultado, respuesta: respuesta.trim() },
    }),
};

/* ------------------------------------------------------------------ seguimiento público */
export const consultarSeguimiento = (codigo: string) =>
  pedir<SeguimientoArcop>("/bff/arcop/seguimiento", { method: "POST", json: { codigo } });
