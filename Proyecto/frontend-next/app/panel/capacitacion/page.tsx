import type { Metadata } from "next";
import { VistaCapacitacion } from "@/components/vistas/VistaCapacitacion";

export const metadata: Metadata = { title: "Capacitación" };

export default function PaginaCapacitacion() {
  return <VistaCapacitacion />;
}
