/** HU-29 · /empresa/documentos — informes, borradores, evidencias y constancias (correcciones 29-10). */
import type { Metadata } from "next";
import { PaginaDocumentos } from "@/components/empresa/PaginaDocumentos";

export const metadata: Metadata = { title: "Mis documentos", robots: { index: false, follow: false } };

export default function Documentos() {
  return <PaginaDocumentos />;
}
