/**
 * HU-32 · /admin/arcop — bandeja de solicitudes de derechos ARCOP del panel interno.
 * Lo protege middleware.ts (sin sesión de admin → /admin/login); la autorización real la
 * hace FastAPI en cada llamada (solo admin_therion).
 */
import type { Metadata } from "next";
import { BandejaArcop } from "@/components/arcop/BandejaArcop";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Panel interno · Solicitudes ARCOP", robots: { index: false, follow: false } };

export default function ArcopAdmin() {
  return <BandejaArcop />;
}
