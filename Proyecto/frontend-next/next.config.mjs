/**
 * Next.js reenvía /api/* al backend FastAPI, así el navegador habla con un
 * solo origen (igual que el nginx del prototipo) y no hace falta CORS.
 *
 *   API_URL  URL interna del backend. Local: http://localhost:8000
 *            En docker compose: http://api:8000
 */
const API_URL = process.env.API_URL ?? "http://localhost:8000";

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
