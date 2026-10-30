import type { Metadata } from "next";
import { VistaSector } from "@/components/vistas/VistaSector";

export const metadata: Metadata = { title: "Sector" };

export default function PaginaSector() {
  return <VistaSector />;
}
