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
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/health", destination: `${API_URL}/health` },
    ];
  },
};

export default nextConfig;
