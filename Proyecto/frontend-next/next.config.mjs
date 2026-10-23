/**
 * Next.js reenvía /api/* al backend FastAPI, así el navegador habla con un
 * solo origen y no hace falta CORS.
 *
 *   API_URL  URL interna del backend. Local: http://localhost:8000
 *            En docker compose: http://api:8000
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Un solo .env para todo el proyecto: Proyecto/.env (junto al docker-compose.yml).
 * Con `npm run dev` fuera de Docker se leen de ahí SOLO las variables del frontend.
 * Lo que ya venga en el entorno (docker compose, la terminal) no se pisa. En la imagen
 * de Docker ese archivo no existe (el contexto de build es esta carpeta) y no pasa nada.
 */
const VARIABLES_FRONTEND = ["API_URL", "NEXT_PUBLIC_DEMO", "TURNSTILE_SITE_KEY", "BFF_SHARED_SECRET", "TRUSTED_PROXY_HOPS"];

function cargarEnvDelProyecto() {
  const archivo = join(dirname(fileURLToPath(import.meta.url)), "..", ".env");
  if (!existsSync(archivo)) return;
  for (const linea of readFileSync(archivo, "utf8").split(/\r?\n/)) {
    const m = /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(linea);
    if (!m || !VARIABLES_FRONTEND.includes(m[1]) || process.env[m[1]] !== undefined) continue;
    let valor = m[2];
    const comillas = /^(["'])(.*)\1$/.exec(valor);
    valor = comillas ? comillas[2] : valor.replace(/\s+#.*$/, "");
    process.env[m[1]] = valor;
  }
}
cargarEnvDelProyecto();

const API_URL = process.env.API_URL || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // HU-19: cabeceras de seguridad para todo el sitio (la CSP la pone middleware.ts)
  async headers() {
    const seguridad = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
    ];
    if (process.env.NODE_ENV === "production") {
      seguridad.push({ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" });
    }
    return [{ source: "/:path*", headers: seguridad }];
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/health", destination: `${API_URL}/health` },
    ];
  },
};

export default nextConfig;
