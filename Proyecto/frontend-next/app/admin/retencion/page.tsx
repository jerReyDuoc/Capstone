/**
 * HU-25 · /admin/retencion — plazo de retención de los usuarios temporales y ejecuciones de la
 * anonimización automática (Oficial de Privacidad).
 * Lo protege middleware.ts (sin sesión de admin → /admin/login); la autorización real la
 * hace FastAPI en cada llamada (solo admin_therion).
 */
import type { Metadata } from "next";
import { PanelRetencion } from "@/components/admin/PanelRetencion";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Panel interno · Retención de datos", robots: { index: false, follow: false } };

export default function RetencionAdmin() {
  return <PanelRetencion />;
}
