import type { Metadata } from "next";
import { RecorridoModulo } from "@/components/formacion/RecorridoModulo";

export const metadata: Metadata = { title: "Módulo formativo", robots: { index: false, follow: false } };

/** HU-26 · /panel/capacitacion/[ruta] — recorrido de un módulo del plan formativo (usuario definitivo). */
export default async function PaginaModulo({ params }: { params: Promise<{ ruta: string }> }) {
  const { ruta } = await params;
  const id = Number(ruta);
  return <RecorridoModulo rutaId={Number.isInteger(id) && id > 0 ? id : null} />;
}
