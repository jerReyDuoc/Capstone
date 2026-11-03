/** HU-16 · /empresa/borradores — borradores de cumplimiento adaptados por el Agente IA. */
import type { Metadata } from "next";
import { Borradores } from "@/components/empresa/Borradores";

export const metadata: Metadata = { title: "Borradores de cumplimiento", robots: { index: false, follow: false } };

export default function PaginaBorradores() {
  return <Borradores />;
}
