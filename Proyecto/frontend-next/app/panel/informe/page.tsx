import type { Metadata } from "next";
import { VistaInforme } from "@/components/vistas/VistaInforme";

export const metadata: Metadata = { title: "Informe" };

export default function PaginaInforme() {
  return <VistaInforme />;
}
