/** /empresa/registro-actividades — Registro de actividades de tratamiento de la empresa (se arma sobre el mapa de datos). */
import type { Metadata } from "next";
import { PasosRegistro } from "@/components/empresa/PasosRegistro";
import { RegistroActividades } from "@/components/empresa/rat/RegistroActividades";

export const metadata: Metadata = { title: "Registro de actividades de tratamiento", robots: { index: false, follow: false } };

export default function PaginaRegistroActividades() {
  // Auditoría UX 16-11 · Fase 8.B: paso del flujo "Arma tu registro"
  return (
    <>
      <PasosRegistro />
      <RegistroActividades />
    </>
  );
}
