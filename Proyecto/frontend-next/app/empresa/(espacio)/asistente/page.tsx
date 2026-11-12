/** /empresa/asistente — Asistente que guía para armar el mapa de datos, el registro de actividades y sus informes. */
import type { Metadata } from "next";
import { AsistenteRegistro } from "@/components/empresa/asistente/AsistenteRegistro";

export const metadata: Metadata = { title: "Asistente de registro", robots: { index: false, follow: false } };

export default function PaginaAsistente() {
  return <AsistenteRegistro />;
}
