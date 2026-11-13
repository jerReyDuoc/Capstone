/**
 * HU-27 · Lista blanca del proxy del panel interno /bff/admin/api/* (lógica pura, probada en tests/).
 *
 * El navegador del administrador no ve su token (cookie httpOnly), así que sus llamadas
 * pasan por app/bff/admin/api/[...ruta]/route.ts, que agrega el Bearer. Solo se reenvían
 * las rutas del panel de HU-27; cualquier otra -> 404. La autorización real (solo
 * admin_therion) la hace FastAPI (app/core/alcance.py: solo_admin).
 */

export type MetodoAdmin = "GET" | "POST" | "PATCH";

const ENTIDADES_MATRIZ = "(controles|brechas|rutas|preguntas-filtro)";

// HU-41: las descargas (PDF y Excel del registro de la plataforma) pasan como binario, con su Content-Disposition
export const TIPOS_PDF_XLSX = ["application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"] as const;

type Regla = { metodo: MetodoAdmin; patron: RegExp; binario?: boolean; tipos?: readonly string[] };

const REGLAS: Regla[] = [
  // Bandeja de solicitudes de contratación (HU-31)
  { metodo: "GET", patron: /^admin\/contrataciones$/ },
  { metodo: "GET", patron: /^admin\/contrataciones\/\d{1,9}$/ },
  { metodo: "PATCH", patron: /^admin\/contrataciones\/\d{1,9}$/ },
  // Empresas cliente (HU-27)
  { metodo: "GET", patron: /^admin\/empresas$/ },
  { metodo: "POST", patron: /^admin\/empresas$/ },
  { metodo: "GET", patron: /^admin\/empresas\/\d{1,9}$/ },
  { metodo: "POST", patron: /^admin\/empresas\/\d{1,9}\/evaluaciones$/ },
  { metodo: "POST", patron: /^admin\/empresas\/\d{1,9}\/usuario\/activacion$/ },
  // HU-28: evaluaciones del panel interno
  { metodo: "GET", patron: /^admin\/evaluaciones$/ },
  // Bitácora (base HU-09)
  { metodo: "GET", patron: /^admin\/bitacora$/ },
  // Catálogo para el formulario
  { metodo: "GET", patron: /^rubros$/ },
  // HU-24: mantenedor de la matriz normativa con versionado
  { metodo: "GET", patron: /^admin\/matriz$/ },
  { metodo: "GET", patron: /^admin\/matriz\/versiones$/ },
  { metodo: "GET", patron: /^admin\/matriz\/versiones\/\d{1,9}$/ },
  { metodo: "GET", patron: /^admin\/matriz\/borrador$/ },
  { metodo: "POST", patron: /^admin\/matriz\/borrador$/ },
  { metodo: "GET", patron: /^admin\/matriz\/borrador\/validacion$/ },
  { metodo: "POST", patron: /^admin\/matriz\/borrador\/(descartar|publicar)$/ },
  { metodo: "POST", patron: new RegExp(`^admin/matriz/borrador/${ENTIDADES_MATRIZ}$`) },
  { metodo: "PATCH", patron: new RegExp(`^admin/matriz/borrador/${ENTIDADES_MATRIZ}/-?\\d{1,9}$`) },
  { metodo: "POST", patron: new RegExp(`^admin/matriz/borrador/${ENTIDADES_MATRIZ}/-?\\d{1,9}/(retirar|restaurar)$`) },
  { metodo: "PATCH", patron: /^admin\/matriz\/borrador\/controles\/-?\d{1,9}\/aplicabilidad$/ },
  // HU-22: bandeja de revisión del Oficial de Cumplimiento
  { metodo: "GET", patron: /^admin\/revision\/(bandeja|resumen)$/ },
  { metodo: "GET", patron: /^admin\/revision\/respuestas\/\d{1,9}$/ },
  { metodo: "PATCH", patron: /^respuestas\/\d{1,9}\/revision$/ },
  { metodo: "PATCH", patron: /^seguridad\/eventos\/\d{1,9}\/revision$/ },
  { metodo: "GET", patron: /^dominios$/ },
  // Correcciones 05-11: rubros desde la matriz normativa
  { metodo: "GET", patron: /^admin\/rubros$/ },
  { metodo: "POST", patron: /^admin\/rubros$/ },
  { metodo: "PATCH", patron: /^admin\/rubros\/\d{1,9}$/ },
  // HU-32: gestión de las solicitudes de derechos ARCOP (la autorización real: solo admin_therion)
  { metodo: "GET", patron: /^arcop\/catalogo$/ },
  { metodo: "GET", patron: /^arcop\/solicitudes$/ },
  { metodo: "GET", patron: /^arcop\/solicitudes\/\d{1,9}$/ },
  { metodo: "PATCH", patron: /^arcop\/solicitudes\/\d{1,9}\/estado$/ },
  { metodo: "POST", patron: /^arcop\/solicitudes\/\d{1,9}\/(prorroga|resolucion)$/ },
  // HU-25: retención de usuarios temporales vencidos (plazo, vista previa, simulación y ejecución)
  { metodo: "GET", patron: /^admin\/retencion$/ },
  { metodo: "PATCH", patron: /^admin\/retencion$/ },
  { metodo: "GET", patron: /^admin\/retencion\/(vista-previa|ejecuciones)$/ },
  { metodo: "POST", patron: /^admin\/retencion\/(simulacion|ejecuciones)$/ },
  // HU-41: registro de tratamiento de la propia plataforma (mapa, RAT, RoPA y revisión interna)
  { metodo: "GET", patron: /^admin\/privacidad-plataforma$/ },
  { metodo: "GET", patron: /^admin\/privacidad-plataforma\/actividades\/[a-z_]{1,40}$/ },
  { metodo: "PATCH", patron: /^admin\/privacidad-plataforma\/ropa-datos$/ },
  { metodo: "POST", patron: /^admin\/privacidad-plataforma\/informes$/ },
  { metodo: "GET", patron: /^admin\/privacidad-plataforma\/informes\/verificacion$/ },
  { metodo: "GET", patron: /^admin\/privacidad-plataforma\/informes\/\d{1,9}\/descarga$/, binario: true, tipos: TIPOS_PDF_XLSX },
  { metodo: "GET", patron: /^admin\/privacidad-plataforma\/mapa\/descarga$/, binario: true, tipos: ["application/pdf"] },
];

const SEGMENTO = /^[A-Za-z0-9_-]{1,64}$/;

export type AutorizacionAdmin =
  | { ok: true; ruta: string; binario?: boolean; tipos?: readonly string[] }
  | { ok: false };

export function autorizarRutaAdmin(metodo: string, segmentos: string[]): AutorizacionAdmin {
  // HU-24: hasta 6 segmentos (admin/matriz/borrador/controles/12/aplicabilidad)
  if (!segmentos.length || segmentos.length > 6 || !segmentos.every((s) => SEGMENTO.test(s))) return { ok: false };
  const ruta = segmentos.join("/");
  const regla = REGLAS.find((r) => r.metodo === metodo && r.patron.test(ruta));
  if (!regla) return { ok: false };
  return regla.binario ? { ok: true, ruta, binario: true, tipos: regla.tipos } : { ok: true, ruta };
}

const QUERY_ADMIN = new Map<string, RegExp>([
  // estados de la bandeja (HU-31) y de las evaluaciones (HU-28)
  // HU-22: + pendiente | revisada | todas (bandeja de revisión)
  // HU-32: + estados de las solicitudes ARCOP
  ["estado", /^(nueva|contactada|contratada|migrada|descartada|en_progreso|completada|pendiente|revisada|todas|recibida|en_revision|pendiente_informacion|en_proceso|resuelta|rechazada|cancelada)$/],
  // HU-32: tipo de derecho y solo solicitudes con plazo vencido
  ["tipo", /^(acceso|rectificacion|supresion|oposicion|portabilidad|bloqueo)$/],
  ["vencidas", /^(true|false)$/],
  // HU-22: + origen de los eventos de seguridad
  ["origen", /^(publica|invitacion|justificacion|evidencia|tutor|tutor_antecedente|borrador)$/],
  ["vista", /^(clasificaciones|eventos)$/],
  ["motivo", /^(seguridad|divergencia|sin_resolver|baja_confianza|resuelta_por_llm|concordante)$/],
  ["evaluacion_id", /^\d{1,9}$/],
  ["dominio_id", /^\d{1,9}$/],
  ["criticidad", /^[A-Za-zÁÉÍÓÚáéíóú]{1,20}$/],
  ["orden", /^(prioridad|reciente)$/],
  ["empresa_id", /^\d{1,9}$/],
  ["incluir_prueba", /^(true|false)$/],
  ["page", /^\d{1,4}$/],
  ["size", /^\d{1,3}$/],
  ["entidad", /^[a-z_]{1,40}$/],
  ["entidad_id", /^\d{1,9}$/],
  ["accion", /^[a-z_.]{1,60}$/],
  // HU-25: plazo a previsualizar (días)
  ["dias", /^\d{1,5}$/],
  // HU-41: código verificable de un informe de la plataforma y formato de descarga
  ["codigo", /^[A-Za-z0-9-]{10,45}$/],
  ["formato", /^(pdf|xlsx)$/],
]);

export function filtrarQueryAdmin(params: URLSearchParams): string {
  const limpios = new URLSearchParams();
  params.forEach((valor, clave) => {
    const patron = QUERY_ADMIN.get(clave);
    if (patron && patron.test(valor)) limpios.append(clave, valor);
  });
  const texto = limpios.toString();
  return texto ? `?${texto}` : "";
}

// HU-24: un control trae textos largos (recomendación, evidencia esperada)
export const MAX_BYTES_JSON_ADMIN = 64 * 1024;
