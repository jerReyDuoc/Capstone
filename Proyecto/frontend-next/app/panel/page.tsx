import type { Metadata } from "next";
import { VistaDiagnostico } from "@/components/vistas/VistaDiagnostico";

export const metadata: Metadata = { title: "Diagnóstico" };

export default function PaginaDiagnostico() {
  return <VistaDiagnostico />;
}
