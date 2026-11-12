/** /empresa/registro-actividades — Registro de actividades de tratamiento de la empresa (se arma sobre el mapa de datos). */
import type { Metadata } from "next";
import { RegistroActividades } from "@/components/empresa/rat/RegistroActividades";

export const metadata: Metadata = { title: "Registro de actividades de tratamiento", robots: { index: false, follow: false } };

export default function PaginaRegistroActividades() {
  return <RegistroActividades />;
}
