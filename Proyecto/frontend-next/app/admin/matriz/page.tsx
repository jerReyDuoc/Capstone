/**
 * HU-24 · /admin/matriz — mantenedor de la matriz normativa con versionado.
 * Lo protege middleware.ts (sin sesión de admin → /admin/login); la autorización real la
 * hace FastAPI en cada llamada (solo admin_therion).
 */
import type { Metadata } from "next";
import { MantenedorMatriz } from "@/components/admin/MantenedorMatriz";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Panel interno · Matriz normativa", robots: { index: false, follow: false } };

export default function MatrizAdmin() {
  return <MantenedorMatriz />;
}
