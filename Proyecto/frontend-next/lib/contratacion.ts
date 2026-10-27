/**
 * HU-31 · "Contratar la plataforma" desde los resultados (lógica pura, probada en
 * tests/hu31_contratacion.test.ts). Sin dependencias de React ni de Next.
 *
 * Contrato con FastAPI (app/api/routes/contratacion.py), siempre a través del BFF:
 *   GET  /bff/api/contratacion/consentimiento                 los dos textos y sus versiones
 *   GET  /bff/api/contratacion/evaluaciones/{id}/solicitud    404 si aún no la envía
 *   POST /bff/api/contratacion/solicitudes                    nombre, cargo, empresa, email,
 *                                                              teléfono opcional, 2 consentimientos, CAPTCHA
 *
 * Las reglas de validación replican las del backend para avisar antes de enviar, pero
 * la validación real es la del servidor.
 */

export type ClaveConsentimiento = "contacto" | "migracion";

export interface TextoConsentimiento {
  clave: ClaveConsentimiento;
  titulo: string;
  texto: string;
  version: string;
}

export type Consentimientos = Record<ClaveConsentimiento, TextoConsentimiento>;

export type EstadoSolicitudPublica = "nueva" | "contactada" | "contratada" | "descartada";

export interface SolicitudPublica {
  id: number;
  evaluacionId: number;
  estado: EstadoSolicitudPublica;
  fechaCreacion: string;
}

export interface FormularioContratacion {
  nombre: string;
  cargo: string;
  empresa: string;
  email: string;
  telefono: string;
  aceptaContacto: boolean;
  aceptaMigracion: boolean;
}

export type CampoFormulario = keyof FormularioContratacion;

export const FORMULARIO_VACIO: FormularioContratacion = {
  nombre: "",
  cargo: "",
  empresa: "",
  email: "",
  telefono: "",
  aceptaContacto: false,
  aceptaMigracion: false,
};

/** Orden de los campos: el resumen de errores los lista así y el foco va al primero. */
export const ORDEN_CAMPOS: CampoFormulario[] = [
  "nombre", "cargo", "empresa", "email", "telefono", "aceptaContacto", "aceptaMigracion",
];

export const LIMITES = {
  nombre: { min: 2, max: 120 },
  cargo: { min: 2, max: 80 },
  empresa: { min: 2, max: 150 },
  email: { max: 100 },
  telefono: { max: 20 },
} as const;

const EMAIL = /^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$/;
const TELEFONO = /^\+?[0-9 ()-]{8,20}$/;

/** Espacios repetidos o en los extremos fuera (igual que el backend). */
export function limpiar(valor: string): string {
  return valor.split(/\s+/).filter(Boolean).join(" ");
}

const NOMBRE_CAMPO: Record<"nombre" | "cargo" | "empresa", string> = {
  nombre: "tu nombre",
  cargo: "tu cargo",
  empresa: "el nombre de tu empresa",
};

/**
 * Errores por campo, redactados como "qué falta + cómo arreglarlo" (WCAG 3.3.1 y 3.3.3).
 * Un objeto vacío significa que el formulario se puede enviar.
 */
export function validarFormulario(f: FormularioContratacion): Partial<Record<CampoFormulario, string>> {
  const errores: Partial<Record<CampoFormulario, string>> = {};
  for (const campo of ["nombre", "cargo", "empresa"] as const) {
    const valor = limpiar(f[campo]);
    const { min, max } = LIMITES[campo];
    if (!valor) errores[campo] = `Escribe ${NOMBRE_CAMPO[campo]}.`;
    else if (valor.length < min) errores[campo] = `Escribe ${NOMBRE_CAMPO[campo]} completo.`;
    else if (valor.length > max) errores[campo] = `Usa como máximo ${max} caracteres.`;
  }
  const email = f.email.trim();
  if (!email) errores.email = "Escribe tu correo para que podamos responderte.";
  else if (email.length > LIMITES.email.max || !EMAIL.test(email))
    errores.email = "Revisa el correo. Debe tener el formato nombre@empresa.cl.";
  const tel = limpiar(f.telefono);
  if (tel && !TELEFONO.test(tel))
    errores.telefono = "Revisa el teléfono. Usa solo números, espacios o +, por ejemplo +56 9 1234 5678.";
  if (!f.aceptaContacto) errores.aceptaContacto = "Marca esta autorización para que podamos contactarte.";
  if (!f.aceptaMigracion)
    errores.aceptaMigracion = "Marca esta autorización para que tu evaluación pueda pasar a tu empresa si contrata.";
  return errores;
}

export function primerError(errores: Partial<Record<CampoFormulario, string>>): CampoFormulario | null {
  return ORDEN_CAMPOS.find((c) => errores[c]) ?? null;
}

/** Cuerpo para POST /api/contratacion/solicitudes. */
export function cuerpoSolicitud(
  evaluacionId: number,
  f: FormularioContratacion,
  textos: Consentimientos,
  captchaToken: string,
) {
  const tel = limpiar(f.telefono);
  return {
    evaluacion_id: evaluacionId,
    nombre: limpiar(f.nombre),
    cargo: limpiar(f.cargo),
    empresa: limpiar(f.empresa),
    email: f.email.trim().toLowerCase(),
    telefono: tel || null,
    consentimiento_contacto: { version: textos.contacto.version, aceptado: f.aceptaContacto },
    consentimiento_migracion: { version: textos.migracion.version, aceptado: f.aceptaMigracion },
    captcha_token: captchaToken,
  };
}

/* ------------------------------------------------------------------ parseo de respuestas */
const esObjeto = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const esTexto = (v: unknown, max: number): v is string => typeof v === "string" && v.length > 0 && v.length <= max;

function parseTexto(v: unknown, clave: ClaveConsentimiento): TextoConsentimiento | null {
  if (!esObjeto(v) || !esTexto(v.texto, 2000) || !esTexto(v.version, 20) || !esTexto(v.titulo, 120)) return null;
  return { clave, titulo: v.titulo, texto: v.texto, version: v.version };
}

export function parseConsentimientos(datos: unknown): Consentimientos | null {
  if (!esObjeto(datos)) return null;
  const contacto = parseTexto(datos.contacto, "contacto");
  const migracion = parseTexto(datos.migracion, "migracion");
  return contacto && migracion ? { contacto, migracion } : null;
}

const ESTADOS_PUBLICOS: EstadoSolicitudPublica[] = ["nueva", "contactada", "contratada", "descartada"];

export function parseSolicitud(datos: unknown): SolicitudPublica | null {
  if (!esObjeto(datos) || typeof datos.id !== "number" || typeof datos.evaluacion_id !== "number") return null;
  const estado = ESTADOS_PUBLICOS.find((e) => e === datos.estado);
  if (!estado) return null;
  return {
    id: datos.id,
    evaluacionId: datos.evaluacion_id,
    estado,
    fechaCreacion: typeof datos.fecha_creacion === "string" ? datos.fecha_creacion : "",
  };
}

/** Lo que ve el encuestado sobre su solicitud (sin jerga interna de la bandeja). */
export const ESTADO_PUBLICO: Record<EstadoSolicitudPublica, { titulo: string; detalle: string; tono: string }> = {
  nueva: {
    titulo: "Solicitud enviada",
    detalle: "El equipo de Therion Labs la revisará y te escribirá al correo que dejaste.",
    tono: "ok",
  },
  contactada: {
    titulo: "Ya estamos en contacto",
    detalle: "Therion Labs se comunicó contigo para avanzar en la contratación.",
    tono: "ok",
  },
  contratada: {
    titulo: "Contratación confirmada",
    detalle: "Recibirás por correo el enlace para activar la cuenta de tu empresa.",
    tono: "ok",
  },
  descartada: {
    titulo: "Solicitud cerrada",
    detalle: "Esta solicitud no siguió adelante y sus datos de contacto se eliminaron.",
    tono: "info",
  },
};

/**
 * Mensajes de los errores del envío (qué pasó + qué hacer). Los que no están aquí
 * usan los de la encuesta pública (lib/encuesta/errores.ts: CAPTCHA, límites, conexión).
 */
export const ERRORES_CONTRATACION: Record<string, { titulo: string; detalle: string }> = {
  SOLICITUD_EXISTENTE: {
    titulo: "Ya enviaste esta solicitud",
    detalle: "Therion Labs ya la recibió y te contactará. No necesitas enviarla de nuevo.",
  },
  CONSENTIMIENTO_DESACTUALIZADO: {
    titulo: "Actualizamos una autorización",
    detalle: "Cambió el texto de una autorización. Léelo de nuevo, márcalo y envía la solicitud.",
  },
  CONSENTIMIENTO_REQUERIDO: {
    titulo: "Faltan autorizaciones",
    detalle: "Para enviar la solicitud debes marcar las dos autorizaciones.",
  },
  EVALUACION_NO_COMPLETADA: {
    titulo: "Primero termina tu evaluación",
    detalle: "Podrás pedir la contratación cuando completes el cuestionario y veas tus resultados.",
  },
  LIMITE_SOLICITUDES: {
    titulo: "Se alcanzó el máximo de solicitudes por hoy",
    detalle: "Desde tu red ya se enviaron varias solicitudes hoy. Inténtalo mañana.",
  },
  EMAIL_INVALIDO: {
    titulo: "Revisa el correo",
    detalle: "Debe tener el formato nombre@empresa.cl.",
  },
};

/** Campo del formulario al que apunta un error del backend (para marcarlo y llevar el foco). */
export function campoDelError(codigo: string, campo?: string, consentimiento?: string): CampoFormulario | null {
  if (codigo === "EMAIL_INVALIDO") return "email";
  if (codigo === "CONSENTIMIENTO_REQUERIDO" || codigo === "CONSENTIMIENTO_DESACTUALIZADO") {
    return consentimiento === "migracion" ? "aceptaMigracion" : consentimiento === "contacto" ? "aceptaContacto" : null;
  }
  if (campo && (ORDEN_CAMPOS as string[]).includes(campo)) return campo as CampoFormulario;
  return null;
}

/** Beneficios del servicio pagado (HU-31 "para"): los muestra el CTA y la página. */
export const BENEFICIOS = [
  {
    icono: "birrete",
    titulo: "Cursos por dimensión",
    texto: "Rutas Inicial, Intermedia y Avanzada según las brechas de tu diagnóstico.",
  },
  {
    icono: "chispa",
    titulo: "Tutor IA",
    texto: "Resuelve dudas de gobernanza de IA y de la Ley 21.719 mientras avanzas.",
  },
  {
    icono: "pdf",
    titulo: "Documentos que cierran brechas",
    texto: "Políticas, registros y procedimientos generados a partir de tus respuestas.",
  },
] as const;
