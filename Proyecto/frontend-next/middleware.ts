/**
 * HU-19 · Middleware (Edge): seguridad de borde de la encuesta pública.
 *
 * 1. Filtro de ráfagas por IP en /bff/encuesta/iniciar y /retomar. Es un PRE-filtro barato
 *    en memoria de la instancia (no reemplaza a los límites reales, que viven en FastAPI
 *    con Redis y no se pueden saltar). Con varias instancias detrás de un balanceador,
 *    cada una cuenta por separado; si despliegan en Vercel, cambien este contador por
 *    @upstash/ratelimit con Upstash Redis (misma interfaz: permitir(ip) → boolean).
 * 2. Bloquea el uso directo, a través del rewrite /api/*, de los endpoints que solo debe
 *    usar el BFF: por ahí la IP llegaría como la del contenedor y el token iría al JS.
 * 3. /encuesta sin cookie de sesión → /retomar (sin exponer nada en la URL).
 * 4. Content-Security-Policy:
 *      - páginas del flujo (/comenzar, /retomar, /encuesta): nonce por petición +
 *        'strict-dynamic', y Turnstile (challenges.cloudflare.com) permitido;
 *      - resto (landing estática, panel): política base sin nonce, porque una página
 *        prerenderizada no puede llevar un nonce distinto en cada petición.
 */
import { NextResponse, type NextRequest } from "next/server";
import { ipCliente } from "@/lib/servidor/peticion";
import { COOKIE_SESION, sesionDelToken } from "@/lib/servidor/sesion";

const DEV = process.env.NODE_ENV !== "production";
const TURNSTILE = "https://challenges.cloudflare.com";

/* ------------------------------------------------------------ 1. ráfagas */
interface Ventana {
  limite: number;
  ms: number;
}
const VENTANAS: Record<string, Ventana> = {
  "/bff/encuesta/iniciar": { limite: 5, ms: 60_000 },
  "/bff/encuesta/retomar": { limite: 10, ms: 60_000 },
};
const golpes = new Map<string, number[]>();
const MAX_CLAVES = 10_000;

function permitir(clave: string, { limite, ms }: Ventana, ahora = Date.now()): { ok: boolean; esperaS: number } {
  const recientes = (golpes.get(clave) ?? []).filter((t) => ahora - t < ms);
  if (recientes.length >= limite) {
    golpes.set(clave, recientes);
    return { ok: false, esperaS: Math.ceil((ms - (ahora - recientes[0])) / 1000) };
  }
  recientes.push(ahora);
  golpes.set(clave, recientes);
  if (golpes.size > MAX_CLAVES) golpes.delete(golpes.keys().next().value as string); // memoria acotada
  return { ok: true, esperaS: 0 };
}

/* ------------------------------------------------------------ 4. CSP */
function cspFlujo(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${TURNSTILE}${DEV ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${DEV ? " ws:" : ""}`,
    `frame-src ${TURNSTILE}`,
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
  ].join("; ");
}

function cspBase(): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${DEV ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${DEV ? " ws:" : ""}`,
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
  ].join("; ");
}

const RUTAS_FLUJO = ["/comenzar", "/retomar", "/encuesta"];
const esFlujo = (p: string) => RUTAS_FLUJO.some((r) => p === r || p.startsWith(`${r}/`));

const SOLO_BFF = [/^\/api\/encuesta-publica(\/|$)/, /^\/api\/auth\/encuestado(\/|$)/];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // 2. Endpoints que solo usa el BFF
  if (SOLO_BFF.some((r) => r.test(pathname))) {
    return new NextResponse(null, { status: 404 });
  }

  // 1. Ráfagas
  const ventana = req.method === "POST" ? VENTANAS[pathname] : undefined;
  if (ventana) {
    const r = permitir(`${pathname}|${ipCliente(req.headers)}`, ventana);
    if (!r.ok) {
      return NextResponse.json(
        {
          error: {
            codigo: "DEMASIADOS_INTENTOS",
            mensaje: "Demasiados intentos seguidos.",
            reintentarEnS: r.esperaS,
          },
        },
        { status: 429, headers: { "Retry-After": String(r.esperaS), "Cache-Control": "no-store" } },
      );
    }
  }
  if (pathname.startsWith("/bff/")) return NextResponse.next();

  // 3. /encuesta exige sesión vigente
  if (pathname === "/encuesta" || pathname.startsWith("/encuesta/")) {
    if (!sesionDelToken(req.cookies.get(COOKIE_SESION)?.value)) {
      const destino = req.nextUrl.clone();
      destino.pathname = "/retomar";
      destino.search = "?motivo=sesion";
      return NextResponse.redirect(destino);
    }
  }

  // 4. CSP
  if (esFlujo(pathname)) {
    const nonce = btoa(crypto.randomUUID());
    const csp = cspFlujo(nonce);
    const headers = new Headers(req.headers);
    headers.set("x-nonce", nonce);
    headers.set("content-security-policy", csp); // Next lo lee para poner el nonce en sus scripts
    const res = NextResponse.next({ request: { headers } });
    res.headers.set("Content-Security-Policy", csp);
    res.headers.set("Cache-Control", "private, no-store");
    return res;
  }
  const res = NextResponse.next();
  res.headers.set("Content-Security-Policy", cspBase());
  return res;
}

export const config = {
  matcher: [
    // Todo menos estáticos de Next y archivos públicos con extensión
    { source: "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|webp|ico|txt)$).*)" },
  ],
};
