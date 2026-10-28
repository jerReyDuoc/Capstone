/**
 * HU-28 · Lista blanca del proxy del usuario definitivo /bff/cliente/api/* (lógica pura,
 * probada en tests/).
 *
 * El cliente entra al espacio de su empresa y, desde ahí, ve los resultados de las
 * evaluaciones migradas con el mismo panel que el encuestado (/panel en modo "cliente").
 * Solo se reenvían esas lecturas (y el envío del informe por correo); todo lo que cambia
 * una evaluación queda fuera: el historial migrado no se reescribe.
 *
 * La autorización real la hace FastAPI (app/core/alcance.py): el rol cliente solo ve las
 * evaluaciones migradas a SU empresa (404 en cualquier otra).
 */

export type MetodoCliente = "GET" | "POST";

interface Regla {
  metodo: MetodoCliente;
  patron: RegExp;
  binario?: boolean;
  conIp?: boolean;
  timeoutMs?: number;
  /** Subida de archivos (multipart): HU-17. */
  archivo?: boolean;
}

const REGLAS: Regla[] = [
  // Espacio de la empresa (HU-28; HU-29 lo amplía)
  { metodo: "GET", patron: /^cliente\/empresa$/ },
  // HU-30: situación del contrato (responde también sin contrato vigente)
  { metodo: "GET", patron: /^cliente\/contrato$/ },
  // Evaluaciones migradas: listado y resultados (lectura)
  { metodo: "GET", patron: /^evaluaciones$/ },
  { metodo: "GET", patron: /^evaluaciones\/\d{1,9}$/ },
  { metodo: "GET", patron: /^evaluaciones\/\d{1,9}\/(respuestas|resumen|comparativa|progreso|plan-formativo)$/ },
  { metodo: "GET", patron: /^evaluaciones\/\d{1,9}\/informe\/pdf$/, binario: true, timeoutMs: 30_000 },
  { metodo: "POST", patron: /^evaluaciones\/\d{1,9}\/informe\/enviar$/, conIp: true, timeoutMs: 45_000 },
  // Catálogos (públicos, sin datos personales)
  { metodo: "GET", patron: /^(brechas|dominios|rubros|rutas-formativas|controles)$/ },
  // HU-26: recorrido de los módulos del plan formativo y avance de la empresa
  { metodo: "GET", patron: /^formacion\/avance$/ },
  { metodo: "GET", patron: /^formacion\/modulos\/\d{1,9}$/ },
  { metodo: "POST", patron: /^formacion\/modulos\/\d{1,9}\/lecciones\/\d{1,4}\/vista$/ },
  { metodo: "POST", patron: /^formacion\/modulos\/\d{1,9}\/verificacion$/ },
  { metodo: "GET", patron: /^formacion\/modulos\/\d{1,9}\/constancia$/, binario: true, timeoutMs: 30_000 },
  // HU-17: remediación (subir evidencia nueva de un control con brecha)
  { metodo: "GET", patron: /^remediacion\/evaluaciones\/\d{1,9}$/ },
  { metodo: "POST", patron: /^remediacion\/respuestas\/\d{1,9}\/evidencias$/, archivo: true, conIp: true, timeoutMs: 60_000 },
  { metodo: "GET", patron: /^remediacion\/evidencias\/\d{1,9}$/ },
];

const SEGMENTO = /^[A-Za-z0-9_-]{1,64}$/;

export type AutorizacionCliente =
  | { ok: true; ruta: string; binario: boolean; conIp: boolean; archivo: boolean; timeoutMs?: number }
  | { ok: false };

export function autorizarRutaCliente(metodo: string, segmentos: string[]): AutorizacionCliente {
  if (!segmentos.length || segmentos.length > 6 || !segmentos.every((s) => SEGMENTO.test(s))) return { ok: false };
  const ruta = segmentos.join("/");
  const regla = REGLAS.find((r) => r.metodo === metodo && r.patron.test(ruta));
  return regla
    ? {
        ok: true, ruta, binario: Boolean(regla.binario), conIp: Boolean(regla.conIp), archivo: Boolean(regla.archivo),
        timeoutMs: regla.timeoutMs,
      }
    : { ok: false };
}

export const MAX_BYTES_JSON_CLIENTE = 16 * 1024;
/** HU-17: evidencias de remediación (el backend corta en EVIDENCIA_MAX_MB, 10 MB por defecto). */
export const MAX_BYTES_ARCHIVO_CLIENTE = 12 * 1024 * 1024;
