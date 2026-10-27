/**
 * HU-27 · /admin/clientes — alta de empresa cliente y usuario definitivo a partir de una
 * solicitud contratada (HU-31), migración de evaluaciones y reenvío de la activación.
 * Lo protege middleware.ts (sin sesión de admin → /admin/login); la autorización real la
 * hace FastAPI en cada llamada.
 */
import type { Metadata } from "next";
import { PanelClientes } from "@/components/admin/PanelClientes";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Panel interno · Empresas cliente", robots: { index: false, follow: false } };

export default function ClientesAdmin() {
  return <PanelClientes />;
}
