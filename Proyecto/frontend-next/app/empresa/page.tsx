/**
 * HU-28 · /empresa — espacio de la empresa del usuario definitivo (HU-29 lo completa).
 * Lo protege middleware.ts (sin sesión de cliente → /ingresar); la autorización real la
 * hace FastAPI en cada llamada.
 */
import type { Metadata } from "next";
import { EspacioEmpresa } from "@/components/empresa/EspacioEmpresa";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Mi empresa", robots: { index: false, follow: false } };

export default function Empresa() {
  return <EspacioEmpresa />;
}
