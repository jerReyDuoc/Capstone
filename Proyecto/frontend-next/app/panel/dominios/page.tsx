import type { Metadata } from "next";
import { VistaDominios } from "@/components/vistas/VistaDominios";

export const metadata: Metadata = { title: "Dominios" };

export default function PaginaDominios() {
  return <VistaDominios />;
}
