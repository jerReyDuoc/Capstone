/**
 * HU-41 · /admin/privacidad — registro de tratamiento de la propia plataforma (mapa de datos, RAT, RoPA y
 * revisión interna), generado desde el inventario de datos.
 * Lo protege middleware.ts (sin sesión de admin → /admin/login); la autorización real la hace FastAPI en
 * cada llamada (solo admin_therion).
 */
import type { Metadata } from "next";
import { PanelPrivacidadPlataforma } from "@/components/admin/PanelPrivacidadPlataforma";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Panel interno · Privacidad de la plataforma", robots: { index: false, follow: false } };

export default function PrivacidadPlataformaAdmin() {
  return <PanelPrivacidadPlataforma />;
}
