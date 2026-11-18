/**
 * Pruebas de navegador (Playwright) sin backend: sesiones y respuestas simuladas del BFF.
 *
 * - Las cookies de sesión son tokens de prueba sin firma válida: el middleware de Next solo LEE
 *   su contenido para redirigir; la firma la verifica FastAPI, que aquí no participa.
 * - Todas las llamadas del navegador a /bff/* y /api/* se responden desde este archivo. Lo que no
 *   tiene respuesta definida devuelve 404 con un error del BFF, como haría el servidor, y queda
 *   anotado en `sinRespuesta` para poder completar la simulación.
 * - Los datos del panel salen de lib/demo.ts (los mismos del modo demo).
 */
import type { BrowserContext, Page, Route } from "@playwright/test";
import { datosApiDemo, DEMO_EVALUACIONES, planDemo } from "../../lib/demo";
import { FIXTURES_ADMIN } from "./fixtures/admin";
import { FIXTURES_EMPRESA } from "./fixtures/empresa";
import { FIXTURES_ENCUESTA } from "./fixtures/encuesta";

export type Rol = "cliente" | "admin" | "encuestado" | "anonimo";

const EVALUACION = DEMO_EVALUACIONES[0].id;

function token(rol: string, sub: number): string {
  const cuerpo = Buffer.from(JSON.stringify({ sub, rol, exp: Math.floor(Date.now() / 1000) + 3600 })).toString("base64url");
  return `${cuerpo}.firma-de-prueba`;
}

/** Cookies con y sin el prefijo __Host- (producción y desarrollo usan nombres distintos). */
export async function iniciarSesion(context: BrowserContext, rol: Rol, baseURL: string) {
  if (rol === "anonimo") return;
  const base = { cliente: "cai_cliente", admin: "cai_admin", encuestado: "cai_sesion" }[rol];
  const valor = token(rol === "admin" ? "admin_therion" : rol, rol === "encuestado" ? EVALUACION : 1);
  const url = new URL(baseURL);
  await context.addCookies([
    { name: base, value: valor, domain: url.hostname, path: "/", httpOnly: true, sameSite: "Lax" },
    { name: `__Host-${base}`, value: valor, domain: url.hostname, path: "/", httpOnly: true, secure: true, sameSite: "Lax" },
  ]);
}

type Respuesta = unknown | ((url: URL, metodo: string) => unknown);
export type TablaFixtures = [RegExp, Respuesta][];

const paginado = <T,>(items: T[]) => ({ items, total: items.length, page: 1, size: 100, pages: 1 });

/** Rutas del panel (diagnóstico, brechas, capacitación…) para cualquier base (/api, /bff/api, /bff/cliente/api). */
function fixturesPanel(): TablaFixtures {
  const d = datosApiDemo(EVALUACION);
  return [
    [/\/evaluaciones\/\d+\/resumen$/, d.resumen],
    [/\/evaluaciones\/\d+\/respuestas$/, paginado(d.respuestas)],
    [/\/evaluaciones\/\d+\/comparativa$/, d.comparativa],
    [/\/evaluaciones\/\d+\/plan-formativo$/, planDemo(EVALUACION)],
    [/\/evaluaciones\/\d+$/, DEMO_EVALUACIONES[0]],
    [/\/evaluaciones$/, paginado(DEMO_EVALUACIONES)],
    [/\/brechas$/, d.catalogo],
    [/\/controles$/, d.controles],
  ];
}

export interface Simulacion {
  sinRespuesta: Set<string>;
}

export async function simular(page: Page, rol: Rol, extra: TablaFixtures = []): Promise<Simulacion> {
  const sinRespuesta = new Set<string>();
  const tablas: TablaFixtures = [
    ...extra,
    [/^\/bff\/cliente\/sesion$/, { activa: rol === "cliente" }],
    [/^\/bff\/encuesta\/sesion$/, rol === "encuestado" ? { activa: true, evaluacionId: EVALUACION, expiraEn: Math.floor(Date.now() / 1000) + 3600 } : { activa: false }],
    ...(rol === "admin" ? FIXTURES_ADMIN : []),
    ...(rol === "cliente" ? FIXTURES_EMPRESA : []),
    ...(rol === "encuestado" ? FIXTURES_ENCUESTA : []),
    ...fixturesPanel(),
  ];

  const responder = async (route: Route) => {
    const req = route.request();
    const url = new URL(req.url());
    const metodo = req.method();
    for (const [patron, valor] of tablas) {
      if (patron.test(url.pathname)) {
        const cuerpo = typeof valor === "function" ? (valor as (u: URL, m: string) => unknown)(url, metodo) : valor;
        if (cuerpo === undefined) continue;
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(cuerpo) });
      }
    }
    sinRespuesta.add(`${metodo} ${url.pathname}`);
    return route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { codigo: "NO_ENCONTRADO", mensaje: "" }, detail: "No encontrado" }),
    });
  };
  await page.route(/\/(bff|api)\//, responder);
  return { sinRespuesta };
}
