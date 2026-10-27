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
  /** El backend necesita la IP del cliente (límites por IP). */
  conIp?: boolean;
  /** Respuesta binaria (PDF): se reenvía tal cual, con su Content-Disposition. */
  binario?: boolean;
  /** Tiempo máximo de espera del backend (ms). */
  timeoutMs?: number;
  /** El cuerpo JSON lleva evaluacion_id: debe ser el de la sesión. */
  cuerpoConEvaluacion?: boolean;
}

const REGLAS: Regla[] = [
  // Evaluación y cuestionario (HU-01/02)
  { metodo: "GET", patron: /^evaluaciones\/(\d+)$/, conEvaluacion: true },
  { metodo: "GET", patron: /^evaluaciones\/(\d+)\/(filtro|controles-aplicables|progreso|respuestas|resumen|comparativa)$/, conEvaluacion: true },
  { metodo: "POST", patron: /^evaluaciones\/(\d+)\/(filtro|cerrar|completar)$/, conEvaluacion: true },
  // HU-12: plan formativo e informe (PDF descargable y por correo)
  { metodo: "GET", patron: /^evaluaciones\/(\d+)\/plan-formativo$/, conEvaluacion: true },
  { metodo: "GET", patron: /^evaluaciones\/(\d+)\/informe\/pdf$/, conEvaluacion: true, binario: true, timeoutMs: 30_000 },
  { metodo: "POST", patron: /^evaluaciones\/(\d+)\/informe\/enviar$/, conEvaluacion: true, conIp: true, timeoutMs: 45_000 },
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
  // HU-31: "Contratar la plataforma" desde los resultados (CAPTCHA y límites por IP en el backend)
  { metodo: "GET", patron: /^contratacion\/consentimiento$/ },
  { metodo: "GET", patron: /^contratacion\/evaluaciones\/(\d+)\/solicitud$/, conEvaluacion: true },
  { metodo: "POST", patron: /^contratacion\/solicitudes$/, conIp: true, cuerpoConEvaluacion: true, timeoutMs: 20_000 },
];

const SEGMENTO = /^[A-Za-z0-9_-]{1,64}$/;

export type Autorizacion =
  | {
      ok: true;
      ruta: string;
      archivo: boolean;
      conIp: boolean;
      binario: boolean;
      timeoutMs?: number;
      cuerpoConEvaluacion: boolean;
    }
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
    return {
      ok: true,
      ruta: destino,
      archivo: Boolean(regla.archivo),
      conIp: Boolean(regla.conIp || regla.archivo),
      binario: Boolean(regla.binario),
      timeoutMs: regla.timeoutMs,
      // POST /respuestas y POST /contratacion/solicitudes llevan evaluacion_id en el cuerpo
      cuerpoConEvaluacion: Boolean(regla.cuerpoConEvaluacion) || destino === "respuestas/",
    };
  }
  return { ok: false, status: 404 };
}

/**
 * Parámetros de consulta permitidos y su largo máximo: paginación y filtros del listado de
 * respuestas, y los filtros de brechas del informe PDF (HU-11/HU-12).
 */
const QUERY_PERMITIDOS = new Map<string, number>([
  ["page", 40], ["size", 40], ["estado_final", 40], ["fuente", 40],
  ["severidad", 80], ["dominio", 80], ["estado", 30], ["q", 80],
]);

export function filtrarQuery(params: URLSearchParams): string {
  const limpios = new URLSearchParams();
  params.forEach((valor, clave) => {
    const max = QUERY_PERMITIDOS.get(clave);
    if (max != null && valor.length <= max) limpios.append(clave, valor);
  });
  const texto = limpios.toString();
  return texto ? `?${texto}` : "";
}

/** POST /respuestas y POST /contratacion/solicitudes llevan evaluacion_id en el cuerpo: debe ser la de la sesión. */
export function cuerpoRespuestaEsDeLaSesion(cuerpo: unknown, evaluacionSesion: number): boolean {
  return (
    typeof cuerpo === "object" &&
    cuerpo !== null &&
    (cuerpo as { evaluacion_id?: unknown }).evaluacion_id === evaluacionSesion
  );
}

export const MAX_BYTES_JSON = 256 * 1024;
export const MAX_BYTES_ARCHIVO = 12 * 1024 * 1024;
