/**
 * HU-19 · Contratos de datos de la encuesta pública.
 *
 * Dos tramos:
 *   navegador ⇄ BFF (app/bff/*)      — nunca lleva el token de sesión
 *   BFF       ⇄ FastAPI (/api/*)     — el BFF agrega el Bearer desde la cookie httpOnly
 *
 * Validadores escritos a mano (sin Zod) para no sumar dependencias: el proyecto solo
 * depende de next/react. Si el equipo adopta Zod, estos parse* se reemplazan 1:1.
 * Todo dato que cruza un tramo pasa por aquí antes de usarse.
 */

export type Resultado<T> = { ok: true; valor: T } | { ok: false; error: string };

const ok = <T,>(valor: T): Resultado<T> => ({ ok: true, valor });
const fallo = (error: string): Resultado<never> => ({ ok: false, error });

const esObjeto = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const esEnteroPositivo = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v > 0;
const esTexto = (v: unknown, max = 10_000): v is string => typeof v === "string" && v.length <= max;

/* ------------------------------------------------------------------ catálogos */

export interface Rubro {
  id: number;
  nombre: string;
}

/** GET /api/rubros → [{ id, nombre_rubro }] */
export function parseRubros(datos: unknown): Rubro[] {
  if (!Array.isArray(datos)) return [];
  return datos
    .filter(esObjeto)
    .filter((r) => esEnteroPositivo(r.id))
    .map((r) => ({ id: r.id as number, nombre: (esTexto(r.nombre_rubro, 100) && r.nombre_rubro.trim()) || `Rubro ${r.id}` }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
}

/* ------------------------------------------------------------------ iniciar */

/** Navegador → BFF: POST /bff/encuesta/iniciar. Sin email: es opcional y va después. */
export interface IniciarEntrada {
  rubroId: number;
  avisoVersion: string;
  avisoAceptado: true;
  captchaToken: string;
}

export function parseIniciarEntrada(datos: unknown): Resultado<IniciarEntrada> {
  if (!esObjeto(datos)) return fallo("cuerpo inválido");
  const { rubroId, avisoVersion, avisoAceptado, captchaToken } = datos;
  if (!esEnteroPositivo(rubroId)) return fallo("rubroId inválido");
  if (!esTexto(avisoVersion, 20) || !avisoVersion) return fallo("avisoVersion inválida");
  if (avisoAceptado !== true) return fallo("aviso no aceptado");
  if (!esTexto(captchaToken, 2048)) return fallo("captchaToken inválido");
  return ok({ rubroId, avisoVersion, avisoAceptado: true, captchaToken });
}

/** BFF → FastAPI: POST /api/encuesta-publica/iniciar */
export function cuerpoIniciarBackend(e: IniciarEntrada) {
  return {
    rubro_id: e.rubroId,
    aviso_legal: { version: e.avisoVersion, aceptado: e.avisoAceptado },
    captcha_token: e.captchaToken,
  };
}

/** FastAPI → BFF (201). El BFF guarda access_token en la cookie y NO lo reenvía. */
export interface IniciadaBackend {
  evaluacion_id: number;
  clave_acceso: string;
  access_token: string;
  expira_en: number;
}

export function parseIniciadaBackend(datos: unknown): Resultado<IniciadaBackend> {
  if (!esObjeto(datos)) return fallo("respuesta inválida");
  const { evaluacion_id, clave_acceso, access_token, expira_en } = datos;
  if (!esEnteroPositivo(evaluacion_id)) return fallo("evaluacion_id");
  if (!esTexto(clave_acceso, 32) || !/^[0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4}$/.test(clave_acceso)) return fallo("clave_acceso");
  if (!esTexto(access_token, 4096) || !access_token.includes(".")) return fallo("access_token");
  if (!esEnteroPositivo(expira_en)) return fallo("expira_en");
  return ok({ evaluacion_id, clave_acceso, access_token, expira_en });
}

/** BFF → navegador (201). La clave se muestra UNA vez; el token jamás sale del servidor. */
export interface Iniciada {
  evaluacionId: number;
  clave: string;
  expiraEn: number;
}

/* ------------------------------------------------------------------ retomar */

/** Navegador → BFF: POST /bff/encuesta/retomar */
export interface RetomarEntrada {
  evaluacionId: number;
  clave: string;
}

/** Igual que el backend: ignora espacios/guiones y acepta minúsculas. 12 caracteres útiles. */
export function normalizarClave(clave: string): string {
  return clave.toUpperCase().replace(/[^0-9A-Z]/g, "");
}

export function formatearClave(clave: string): string {
  const c = normalizarClave(clave).slice(0, 12);
  return c.replace(/(.{4})(?=.)/g, "$1-");
}

export function parseRetomarEntrada(datos: unknown): Resultado<RetomarEntrada> {
  if (!esObjeto(datos)) return fallo("cuerpo inválido");
  const id = typeof datos.evaluacionId === "string" ? Number(datos.evaluacionId) : datos.evaluacionId;
  if (!esEnteroPositivo(id) || id > 2_147_483_647) return fallo("Número de evaluación inválido");
  if (!esTexto(datos.clave, 64)) return fallo("Clave inválida");
  const clave = normalizarClave(datos.clave);
  if (clave.length !== 12) return fallo("La clave tiene 12 caracteres (formato XXXX-XXXX-XXXX)");
  return ok({ evaluacionId: id, clave });
}

/** FastAPI → BFF: POST /api/auth/encuestado (200) */
export interface LoginEncuestadoBackend {
  access_token: string;
  usuario_id: number;
  expira_en_min: number;
}

export function parseLoginEncuestado(datos: unknown): Resultado<LoginEncuestadoBackend> {
  if (!esObjeto(datos)) return fallo("respuesta inválida");
  const { access_token, usuario_id, expira_en_min, rol } = datos;
  if (rol !== "encuestado") return fallo("rol");
  if (!esTexto(access_token, 4096) || !access_token.includes(".")) return fallo("access_token");
  if (!esEnteroPositivo(usuario_id)) return fallo("usuario_id");
  if (!esEnteroPositivo(expira_en_min)) return fallo("expira_en_min");
  return ok({ access_token, usuario_id, expira_en_min });
}

/* ------------------------------------------------------------------ sesión y email */

/** GET /bff/encuesta/sesion */
export type Sesion = { activa: true; evaluacionId: number; expiraEn: number } | { activa: false };

/** PATCH /bff/encuesta/email — null borra el email. */
export function parseEmailEntrada(datos: unknown): Resultado<{ email: string | null }> {
  if (!esObjeto(datos)) return fallo("cuerpo inválido");
  if (datos.email === null || datos.email === "") return ok({ email: null });
  if (!esTexto(datos.email, 100)) return fallo("Correo demasiado largo");
  const email = datos.email.trim().toLowerCase();
  if (!/^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$/.test(email)) return fallo("Revisa el formato del correo");
  return ok({ email });
}

/* ------------------------------------------------------------------ límites */

/** GET /api/encuesta-publica/limites (vía /bff/api/encuesta-publica/limites) */
export interface Limites {
  evaluacionId: number;
  evidencias: { usadas: number; limite: number; restantes: number };
  validacionesIa: { usadas: number; limite: number; restantes: number | null; reiniciaEn: string };
  servicioIaDisponible: boolean;
}

export function parseLimites(datos: unknown): Resultado<Limites> {
  if (!esObjeto(datos) || !esObjeto(datos.evidencias) || !esObjeto(datos.validaciones_ia)) return fallo("límites");
  const ev = datos.evidencias;
  const ia = datos.validaciones_ia;
  const n = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
  return ok({
    evaluacionId: n(datos.evaluacion_id),
    evidencias: { usadas: n(ev.usadas), limite: n(ev.limite), restantes: n(ev.restantes) },
    validacionesIa: {
      usadas: n(ia.usadas),
      limite: n(ia.limite),
      restantes: typeof ia.restantes === "number" ? ia.restantes : null,
      reiniciaEn: esTexto(ia.reinicia_en, 40) ? ia.reinicia_en : "",
    },
    servicioIaDisponible: datos.servicio_ia_disponible !== false,
  });
}

/* ------------------------------------------------------------------ errores */

/** Forma única de error hacia el navegador (BFF y proxy). */
export interface ErrorEncuesta {
  codigo: string;
  mensaje: string;
  reintentarEnS?: number;
  reiniciaEn?: string;
  versionVigente?: string;
  /** HU-31: campo del formulario que rechazó el backend (p. ej. "telefono"). */
  campo?: string;
  /** HU-31: qué consentimiento falta o cambió ("contacto" | "migracion"). */
  consentimiento?: string;
  /** HU-29: 409 EVALUACION_EN_CURSO trae la evaluación abierta para retomarla. */
  evaluacionId?: number;
}

/**
 * Convierte el error de FastAPI ({detail: {codigo, mensaje, ...}} o {detail: "texto"}
 * o la lista de errores de validación de Pydantic) en ErrorEncuesta.
 */
export function parseErrorBackend(status: number, cuerpo: unknown, retryAfter?: string | null): ErrorEncuesta {
  const detalle = esObjeto(cuerpo) ? cuerpo.detail : undefined;
  let codigo = `HTTP_${status}`;
  let mensaje = "";
  let extra: Partial<ErrorEncuesta> = {};
  if (esObjeto(detalle)) {
    if (esTexto(detalle.codigo, 60)) codigo = detalle.codigo;
    if (esTexto(detalle.mensaje, 500)) mensaje = detalle.mensaje;
    if (typeof detalle.reintentar_en_s === "number") extra.reintentarEnS = detalle.reintentar_en_s;
    if (esTexto(detalle.reinicia_en, 40)) extra.reiniciaEn = detalle.reinicia_en;
    if (esTexto(detalle.version_vigente, 20)) extra.versionVigente = detalle.version_vigente;
    if (esTexto(detalle.campo, 40) && /^[a-z_]+$/.test(detalle.campo)) extra.campo = detalle.campo;
    if (detalle.consentimiento === "contacto" || detalle.consentimiento === "migracion") {
      extra.consentimiento = detalle.consentimiento;
    }
    if (Number.isInteger(detalle.evaluacion_id) && (detalle.evaluacion_id as number) > 0) {
      extra.evaluacionId = detalle.evaluacion_id as number;
    }
  } else if (esTexto(detalle, 500)) {
    mensaje = detalle;
  } else if (Array.isArray(detalle) && status === 422) {
    codigo = "DATOS_INVALIDOS";
  }
  if (extra.reintentarEnS === undefined && retryAfter && /^\d+$/.test(retryAfter)) {
    extra.reintentarEnS = Number(retryAfter);
  }
  return { codigo, mensaje, ...extra };
}
