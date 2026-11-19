/**
 * /empresa/asistente — Corrección 18-11: el asistente de registro a página completa, con sus dos pestañas
 * («Preguntar» y «Revisar mi registro»). Corrección 18-11 (2): ya no tiene entrada en el menú; se llega desde el
 * panel del asistente (botón «Asistente» del mapa de datos y del registro de actividades).
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
