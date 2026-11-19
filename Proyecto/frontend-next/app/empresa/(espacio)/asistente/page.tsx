/**
 * /empresa/asistente — Corrección 18-11: el asistente de registro como sección propia del menú
 * («Privacidad y registro → Asistente»), con sus dos pestañas («Preguntar» y «Revisar mi registro»).
 * El botón flotante del mapa de datos y del registro de actividades sigue abriendo el mismo asistente, con la
 * misma conversación de la cuenta. `?vista=mapa|registro` elige sobre qué se pregunta.
 */
import type { Metadata } from "next";
import { SeccionAsistente } from "@/components/empresa/guia/SeccionAsistente";

export const metadata: Metadata = { title: "Asistente de registro", robots: { index: false, follow: false } };

export default async function PaginaAsistente({ searchParams }: { searchParams: Promise<{ vista?: string }> }) {
  const { vista } = await searchParams;
  return <SeccionAsistente vistaInicial={vista === "mapa" ? "mapa" : "registro"} />;
}
