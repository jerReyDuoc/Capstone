/** /empresa/registro-actividades/revision — Revisión interna del registro (auditoría interna del propio usuario). */
import type { Metadata } from "next";
import { RevisionInterna } from "@/components/empresa/rat/revision/RevisionInterna";

export const metadata: Metadata = { title: "Revisión interna del registro", robots: { index: false, follow: false } };

export default function PaginaRevisionInterna() {
  return <RevisionInterna />;
}
