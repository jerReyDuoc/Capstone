/** HU-29 · /empresa/evaluaciones — historial, evolución y reevaluación (correcciones 29-10). */
import type { Metadata } from "next";
import { MisEvaluaciones } from "@/components/empresa/MisEvaluaciones";

export const metadata: Metadata = { title: "Mis evaluaciones", robots: { index: false, follow: false } };

export default function Evaluaciones() {
  return <MisEvaluaciones />;
}
