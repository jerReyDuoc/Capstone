/**
 * HU-32 · /empresa/mis-derechos — derechos ARCOP del usuario definitivo, desde la interfaz
 * contratada. Disponible siempre, con o sin contrato vigente (HU-30). Lo protege
 * middleware.ts (sin sesión de cliente → /ingresar); la autorización real la hace FastAPI.
 */
import type { Metadata } from "next";
import { DerechosTitular } from "@/components/arcop/DerechosTitular";

export const metadata: Metadata = { title: "Mis derechos sobre mis datos", robots: { index: false, follow: false } };

export default function MisDerechosEmpresa() {
  return <DerechosTitular perfil="cliente" />;
}
