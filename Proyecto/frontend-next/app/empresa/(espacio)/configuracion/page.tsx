/** Auditoría UX 16-11 · /empresa/configuracion — ficha de la empresa (RUT, rubro, contrato) y tu usuario. */
import type { Metadata } from "next";
import { FichaEmpresa } from "@/components/empresa/EspacioEmpresa";

export const metadata: Metadata = { title: "Configuración", robots: { index: false, follow: false } };

export default function Configuracion() {
  return <FichaEmpresa />;
}
