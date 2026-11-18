/**
 * Auditoría UX 16-11 · Fase 8.B: /empresa/registro — entrada única "Arma tu registro de actividades".
 * Lleva directo al paso pendiente (mapa de datos → asistente → revisar el registro).
 */
import type { Metadata } from "next";
import { EntradaRegistro } from "@/components/empresa/EntradaRegistro";

export const metadata: Metadata = { title: "Arma tu registro de actividades", robots: { index: false, follow: false } };

export default function PaginaEntradaRegistro() {
  return <EntradaRegistro />;
}
