/** HU-28 · /empresa — Mi empresa: datos de la empresa y su contrato (correcciones 29-10). */
import type { Metadata } from "next";
import { EspacioEmpresa } from "@/components/empresa/EspacioEmpresa";

export const metadata: Metadata = { title: "Mi empresa", robots: { index: false, follow: false } };

export default function Empresa() {
  return <EspacioEmpresa />;
}
