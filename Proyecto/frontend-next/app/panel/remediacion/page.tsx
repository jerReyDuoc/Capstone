import type { Metadata } from "next";
import { VistaRemediacion } from "@/components/remediacion/VistaRemediacion";

export const metadata: Metadata = { title: "Cerrar brechas", robots: { index: false, follow: false } };

/** HU-17 · /panel/remediacion — subir evidencia nueva para re-evaluar los controles con brecha. */
export default function PaginaRemediacion() {
  return <VistaRemediacion />;
}
