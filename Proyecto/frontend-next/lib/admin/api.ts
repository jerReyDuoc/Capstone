/**
 * HU-27 · Contratos y llamadas del panel interno (navegador → /bff/admin/*).
 * Los tipos reflejan las respuestas de FastAPI /api/admin/* (app/api/routes/admin_clientes.py).
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";

export type EstadoSolicitud = "pendiente" | "contratada" | "migrada" | "descartada";
export type EstadoUsuario = "pendiente_activacion" | "activo" | "bloqueado";

export interface EvaluacionResumen {
  id: number;
  origen?: string;
  estado_progreso?: string | null;
  fecha_inicio?: string | null;
  completada?: boolean;
  rubro_id?: number | null;
  rubro?: string | null;
  puntaje_general?: number | null;
  empresa_id?: number | null;
  fecha_migracion?: string | null;
}

export interface Solicitud {
  id: number;
  estado: EstadoSolicitud;
  contacto: { nombre: string | null; email: string | null; telefono: string | null };
  razon_social_declarada: string | null;
  autoriza_migracion: boolean;
  fecha_creacion: string;
  empresa_id: number | null;
  evaluacion: EvaluacionResumen;
}

export interface UsuarioDefinitivo {
  id: number;
  nombre: string;
  email: string;
  rol: "cliente";
  estado: EstadoUsuario;
  fecha_activacion: string | null;
  ultimo_acceso: string | null;
}

export interface Empresa {
  id: number;
  razon_social: string;
  rut: string;
  rubro_id: number;
  fecha_inicio_contrato: string;
  fecha_termino_contrato: string;
  contrato_vigente: boolean;
  usuario: UsuarioDefinitivo | null;
  evaluaciones?: number;
}

export interface Migrada {
  solicitud_id: number;
  evaluacion_id: number;
  respuestas: number;
  evidencias: number;
  dimensiones_resumen: number;
  plan_formativo: boolean;
  informe_pdf: boolean;
}

export interface Activacion {
  enviado: boolean;
  modo: string | null;
  motivo: string | null;
  mensaje: string;
}

export interface ResultadoAlta {
  empresa: Empresa;
  usuario: UsuarioDefinitivo;
  evaluaciones_migradas: Migrada[];
  activacion: Activacion;
}

export interface FilaBitacora {
  id: number;
  fecha: string;
  actor_rol: string;
  actor_id: number | null;
  accion: string;
  entidad: string;
  entidad_id: number | null;
  resultado: string;
  detalle: Record<string, unknown> | null;
}

export interface Pagina<T> {
  items: T[];
  total: number;
}

export interface AltaEntrada {
  empresa: {
    razon_social: string;
    rut: string;
    rubro_id: number;
    fecha_inicio_contrato: string;
    fecha_termino_contrato: string;
  };
  usuario: { nombre: string; email: string };
  solicitudes_ids: number[];
}

const BASE = "/bff/admin/api";

export const api = {
  solicitudes: (estado?: EstadoSolicitud) =>
    pedir<Pagina<Solicitud>>(`${BASE}/admin/contrataciones?size=100${estado ? `&estado=${estado}` : ""}`),
  cambiarEstado: (id: number, estado: EstadoSolicitud) =>
    pedir<Solicitud>(`${BASE}/admin/contrataciones/${id}`, { method: "PATCH", json: { estado } }),
  empresas: () => pedir<Pagina<Empresa>>(`${BASE}/admin/empresas?size=100`),
  alta: (entrada: AltaEntrada) => pedir<ResultadoAlta>(`${BASE}/admin/empresas`, { method: "POST", json: entrada }),
  asociar: (empresaId: number, solicitudes: number[]) =>
    pedir<{ evaluaciones_migradas: Migrada[] }>(`${BASE}/admin/empresas/${empresaId}/evaluaciones`, {
      method: "POST",
      json: { solicitudes_ids: solicitudes },
    }),
  reenviar: (empresaId: number) =>
    pedir<{ activacion: Activacion }>(`${BASE}/admin/empresas/${empresaId}/usuario/activacion`, { method: "POST" }),
  bitacora: () => pedir<Pagina<FilaBitacora>>(`${BASE}/admin/bitacora?size=100`),
  rubros: () => pedir<{ id: number; nombre_rubro: string | null }[]>(`${BASE}/rubros`),
};

export interface ErrorAdmin {
  status: number;
  codigo: string;
  mensaje: string;
  campo?: string;
  solicitud_id?: number;
}

export function comoErrorAdmin(e: unknown): ErrorAdmin {
  if (e instanceof ErrorBff) {
    const info = e.info as unknown as Record<string, unknown>;
    return {
      status: e.status,
      codigo: e.info.codigo,
      mensaje: e.info.mensaje || mensajePorCodigo(e.info.codigo),
      campo: typeof info.campo === "string" ? info.campo : undefined,
      solicitud_id: typeof info.solicitud_id === "number" ? info.solicitud_id : undefined,
    };
  }
  return { status: 0, codigo: "DESCONOCIDO", mensaje: "Ocurrió un error inesperado." };
}

function mensajePorCodigo(codigo: string): string {
  switch (codigo) {
    case "SESION_EXPIRADA":
      return "Tu sesión terminó. Vuelve a iniciar sesión.";
    case "SIN_CONEXION":
      return "No pudimos conectar con el servidor.";
    case "NO_AUTORIZADO":
      return "Tu usuario no tiene permiso para esta acción.";
    default:
      return "No se pudo completar la acción.";
  }
}

/** Selección válida para el alta: contratada, con autorización y evaluación completada. */
export function seleccionable(s: Solicitud): boolean {
  return s.estado === "contratada" && s.autoriza_migracion && Boolean(s.evaluacion.completada) && !s.empresa_id;
}

const RUT_LIMPIO = /^(\d{1,8})([0-9K])$/;

/** Validación del RUT en el formulario (la definitiva la hace el backend, app/core/rut.py). */
export function rutValido(rut: string): boolean {
  const limpio = rut.replace(/[.\s-]/g, "").toUpperCase();
  const m = RUT_LIMPIO.exec(limpio);
  if (!m) return false;
  const cuerpo = m[1].replace(/^0+/, "") || "0";
  if (Number(cuerpo) < 1_000_000) return false;
  let suma = 0;
  let factor = 2;
  for (let i = cuerpo.length - 1; i >= 0; i--) {
    suma += Number(cuerpo[i]) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const resto = 11 - (suma % 11);
  const dv = resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
  return dv === m[2];
}

/** 76086428-5 → 76.086.428-5 */
export function formatearRut(rut: string): string {
  const [cuerpo, dv] = rut.split("-");
  if (!cuerpo || !dv) return rut;
  return `${cuerpo.replace(/\B(?=(\d{3})+(?!\d))/g, ".")}-${dv}`;
}

export const ETIQUETA_ESTADO_SOLICITUD: Record<EstadoSolicitud, { texto: string; tono: string }> = {
  pendiente: { texto: "Pendiente", tono: "medio" },
  contratada: { texto: "Contratada", tono: "ok" },
  migrada: { texto: "Migrada", tono: "info" },
  descartada: { texto: "Descartada", tono: "alto" },
};

export const ETIQUETA_ESTADO_USUARIO: Record<EstadoUsuario, { texto: string; tono: string }> = {
  pendiente_activacion: { texto: "Pendiente de activación", tono: "medio" },
  activo: { texto: "Activo", tono: "ok" },
  bloqueado: { texto: "Bloqueado", tono: "alto" },
};
