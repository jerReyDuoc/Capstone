"use client";

/**
 * Corrección 18-11 · Barra superior delgada del panel (/panel/*) y del espacio de la empresa (/empresa/*),
 * sobre el contenido y a la derecha de la barra lateral. Hoy lleva el selector de tema.
 * En móvil no se muestra: el selector va en la barra superior compacta (Sidebar → .barra-movil).
 */
import { SelectorTema } from "@/components/ui/SelectorTema";
import { usePanelOpcional } from "@/hooks/usePanel";

export function BarraSuperior() {
  const panel = usePanelOpcional();
  const cliente = (panel?.modo ?? "cliente") === "cliente";
  return (
    <div className="barra-superior">
      <SelectorTema cuenta={cliente ? "cliente" : "ninguna"} />
    </div>
  );
}
