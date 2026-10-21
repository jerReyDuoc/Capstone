/**
 * HU-19 · Lista blanca del proxy autenticado /bff/api/* (lógica pura, probada en tests/).
 *
 * El navegador no puede adjuntar el token (la cookie es httpOnly), así que las llamadas
 * del encuestado pasan por app/bff/api/[...ruta]/route.ts, que agrega el Bearer.
 * Solo se reenvían las rutas que el encuestado necesita; cualquier otra -> 404.
 *
 * Segunda barrera (la primera es el backend, app/core/alcance.py): si la ruta lleva un
 * id de evaluación, debe ser el de la sesión.
 */

export type Metodo = "GET" | "POST" | "PUT" | "PATCH";

interface Regla {
  metodo: Metodo;
  patron: RegExp;
  /** La ruta lleva el id de la evaluación en el primer grupo de captura. */
  conEvaluacion?: boolean;
  /** Subida de archivos (multipart): otro límite de tamaño y de tiempo. */
  archivo?: boolean;
}

const REGLAS: Regla[] = [
  // Evaluación y cuestionario (HU-01/02)
  { metodo: "GET", patron: /^evaluaciones\/(\d+)$/, conEvaluacion: true },
  { metodo: "GET", patron: /^evaluaciones\/(\d+)\/(filtro|controles-aplicables|progreso|respuestas|resumen|comparativa)$/, conEvaluacion: true },
  { metodo: "POST", patron: /^evaluaciones\/(\d+)\/(filtro|cerrar|completar)$/, conEvaluacion: true },
  { metodo: "POST", patron: /^respuestas$/ },
  { metodo: "GET", patron: /^respuestas\/\d+$/ },
  { metodo: "PUT", patron: /^respuestas\/\d+$/ },
  { metodo: "POST", patron: /^respuestas\/\d+\/evidencias$/, archivo: true },
  { metodo: "GET", patron: /^evidencias\/\d+$/ },
  // Catálogos (públicos, sin datos personales)
  { metodo: "GET", patron: /^(brechas|dominios|rubros|rutas-formativas|controles)$/ },
  // Límites de la encuesta pública (HU-19)
  { metodo: "GET", patron: /^encuesta-publica\/limites$/ },
  // Derechos ARCOP del encuestado (HU-08)
  { metodo: "GET", patron: /^arcop\/catalogo$/ },
  { metodo: "GET", patron: /^arcop\/solicitudes(\/\d+)?$/ },
  { metodo: "POST", patron: /^arcop\/solicitudes$/ },
  { metodo: "POST", patron: /^arcop\/solicitudes\/\d+\/(cancelacion|informacion)$/ },
];

const SEGMENTO = /^[A-Za-z0-9_-]{1,64}$/;

export type Autorizacion =
  | { ok: true; ruta: string; archivo: boolean }
  | { ok: false; status: 404 };

export function autorizarRuta(metodo: string, segmentos: string[], evaluacionSesion: number): Autorizacion {
  // Nada de "..", "%2F", vacíos ni segmentos raros: cada segmento es un identificador simple
  if (!segmentos.length || segmentos.length > 6 || !segmentos.every((s) => SEGMENTO.test(s))) {
    return { ok: false, status: 404 };
  }
  const ruta = segmentos.join("/");
  for (const regla of REGLAS) {
    if (regla.metodo !== metodo) continue;
    const m = regla.patron.exec(ruta);
    if (!m) continue;
    if (regla.conEvaluacion && Number(m[1]) !== evaluacionSesion) return { ok: false, status: 404 };
    // FastAPI define POST /api/respuestas/ con barra final
    const destino = ruta === "respuestas" ? "respuestas/" : ruta;
    return { ok: true, ruta: destino, archivo: Boolean(regla.archivo) };
  }
  return { ok: false, status: 404 };
}

/** Parámetros de consulta permitidos (paginación y filtros del listado de respuestas). */
const QUERY_PERMITIDOS = new Set(["page", "size", "estado_final", "fuente"]);

export function filtrarQuery(params: URLSearchParams): string {
  const limpios = new URLSearchParams();
  params.forEach((valor, clave) => {
    if (QUERY_PERMITIDOS.has(clave) && valor.length <= 40) limpios.append(clave, valor);
  });
  const texto = limpios.toString();
  return texto ? `?${texto}` : "";
}

/** POST /respuestas lleva evaluacion_id en el cuerpo: debe ser la de la sesión. */
export function cuerpoRespuestaEsDeLaSesion(cuerpo: unknown, evaluacionSesion: number): boolean {
  return (
    typeof cuerpo === "object" &&
    cuerpo !== null &&
    (cuerpo as { evaluacion_id?: unknown }).evaluacion_id === evaluacionSesion
  );
}

export const MAX_BYTES_JSON = 256 * 1024;
export const MAX_BYTES_ARCHIVO = 12 * 1024 * 1024;
