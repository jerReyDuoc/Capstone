/**
 * HU-32 · /panel/mis-derechos — derechos ARCOP del usuario temporal (entró con su N.º de
 * evaluación + clave). Vive dentro del panel, con la misma barra lateral que sus resultados.
 * El usuario definitivo tiene su propia página en /empresa/mis-derechos.
 */
import type { Metadata } from "next";
import { PanelMisDerechos } from "@/components/arcop/PanelMisDerechos";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Mis derechos sobre mis datos", robots: { index: false, follow: false } };

export default function MisDerechosPanel() {
  return <PanelMisDerechos />;
}
