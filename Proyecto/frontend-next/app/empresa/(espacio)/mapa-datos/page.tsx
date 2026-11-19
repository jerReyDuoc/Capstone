/** /empresa/mapa-datos — Mapa de datos personales de la empresa (base del registro de actividades de tratamiento). */
import type { Metadata } from "next";
import { MapaDatos } from "@/components/empresa/mapa/MapaDatos";

export const metadata: Metadata = { title: "Mapa de datos personales", robots: { index: false, follow: false } };

export default function PaginaMapaDatos() {
  // Corrección 18-11 (2): sin el indicador de pasos; el mapa y el registro tienen cada uno su entrada en el menú
  return <MapaDatos />;
}
