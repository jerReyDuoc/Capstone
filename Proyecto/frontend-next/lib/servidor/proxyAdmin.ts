/**
 * HU-27 · Lista blanca del proxy del panel interno /bff/admin/api/* (lógica pura, probada en tests/).
 *
 * El navegador del administrador no ve su token (cookie httpOnly), así que sus llamadas
 * pasan por app/bff/admin/api/[...ruta]/route.ts, que agrega el Bearer. Solo se reenvían
 * las rutas del panel de HU-27; cualquier otra -> 404. La autorización real (solo
 * admin_therion) la hace FastAPI (app/core/alcance.py: solo_admin).
 */

export type MetodoAdmin = "GET" | "POST" | "PATCH";

const REGLAS: { metodo: MetodoAdmin; patron: RegExp }[] = [
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
];

const SEGMENTO = /^[A-Za-z0-9_-]{1,64}$/;

export type AutorizacionAdmin = { ok: true; ruta: string } | { ok: false };

export function autorizarRutaAdmin(metodo: string, segmentos: string[]): AutorizacionAdmin {
  if (!segmentos.length || segmentos.length > 5 || !segmentos.every((s) => SEGMENTO.test(s))) return { ok: false };
  const ruta = segmentos.join("/");
  const permitida = REGLAS.some((r) => r.metodo === metodo && r.patron.test(ruta));
  return permitida ? { ok: true, ruta } : { ok: false };
}

const QUERY_ADMIN = new Map<string, RegExp>([
  // estados de la bandeja (HU-31) y de las evaluaciones (HU-28)
  ["estado", /^(nueva|contactada|contratada|migrada|descartada|en_progreso|completada)$/],
  ["origen", /^(publica|invitacion)$/],
  ["empresa_id", /^\d{1,9}$/],
  ["incluir_prueba", /^(true|false)$/],
  ["page", /^\d{1,4}$/],
  ["size", /^\d{1,3}$/],
  ["entidad", /^[a-z_]{1,40}$/],
  ["entidad_id", /^\d{1,9}$/],
  ["accion", /^[a-z_.]{1,60}$/],
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

export const MAX_BYTES_JSON_ADMIN = 32 * 1024;
