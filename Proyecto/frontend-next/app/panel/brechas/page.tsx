import type { Metadata } from "next";
import { VistaBrechas } from "@/components/vistas/VistaBrechas";

export const metadata: Metadata = { title: "Brechas" };

export default function PaginaBrechas() {
  return <VistaBrechas />;
}
