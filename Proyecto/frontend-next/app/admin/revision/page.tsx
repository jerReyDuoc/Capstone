/**
 * HU-22 · /admin/revision — bandeja del Oficial de Cumplimiento: divergencias de la IA y
 * eventos de seguridad para confirmar o corregir la clasificación final.
 * Lo protege middleware.ts (sin sesión de admin → /admin/login); la autorización real la
 * hace FastAPI en cada llamada (solo admin_therion).
 */
import type { Metadata } from "next";
import { BandejaRevision } from "@/components/admin/BandejaRevision";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Panel interno · Bandeja de revisión", robots: { index: false, follow: false } };

export default function RevisionAdmin() {
  return <BandejaRevision />;
}
