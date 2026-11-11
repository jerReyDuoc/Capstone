/** /empresa/mapa-datos — Mapa de datos personales de la empresa (base del registro de actividades de tratamiento). */
import type { Metadata } from "next";
import { MapaDatos } from "@/components/empresa/mapa/MapaDatos";

export const metadata: Metadata = { title: "Mapa de datos personales", robots: { index: false, follow: false } };

export default function PaginaMapaDatos() {
  return <MapaDatos />;
}
