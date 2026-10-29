/**
 * HU-29 · /empresa/evaluacion/[id] — el usuario definitivo responde una reevaluación de su
 * empresa con el mismo cuestionario del autodiagnóstico, por su BFF (/bff/cliente/api).
 * Lo protege middleware.ts (sin sesión de cliente → /ingresar); que la evaluación sea de su
 * empresa lo decide FastAPI (404 si no lo es).
 */
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ReevaluacionEmpresa } from "@/components/empresa/ReevaluacionEmpresa";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Reevaluación", robots: { index: false, follow: false } };

export default async function Reevaluacion({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d{1,9}$/.test(id)) notFound();
  return <ReevaluacionEmpresa evaluacionId={Number(id)} />;
}
