"use client";

/**
 * Madurez por dimensión en el Diagnóstico: radar (por defecto) o barras.
 *
 * - En pantallas de 600 px o más se puede elegir "Radar" o "Barras".
 * - En pantallas angostas (celular) el radar no se lee bien: se muestran siempre las barras
 *   (mismos datos, misma tabla alternativa). Lo decide el CSS (.solo-amplio / .solo-angosto),
 *   así no hay saltos al cargar la página. Lo oculto con display:none tampoco lo leen los
 *   lectores de pantalla, de modo que el contenido no se duplica.
 * - Con menos de 3 dimensiones un radar no forma una figura: se muestran las barras.
 */
import { useState } from "react";
import type { DominioVista } from "@/lib/types";
import { BarrasComparadas } from "./BarrasComparadas";
import { RadarMadurez } from "./RadarMadurez";

type Vista = "radar" | "barras";

export function MadurezPorDominio({
  dominios,
  onSeleccionar,
}: {
  dominios: DominioVista[];
  onSeleccionar?: (d: DominioVista) => void;
}) {
  const [vista, setVista] = useState<Vista>("radar");
  const radarPosible = dominios.length >= 3;

  if (!radarPosible) return <BarrasComparadas dominios={dominios} onSeleccionar={onSeleccionar} />;

  const selector = (
    <div className="selector-vista solo-amplio" role="group" aria-label="Tipo de gráfico">
      {(["radar", "barras"] as const).map((v) => (
        <button key={v} type="button" className="selector-vista-opcion" aria-pressed={vista === v} onClick={() => setVista(v)}>
          {v === "radar" ? "Radar" : "Barras"}
        </button>
      ))}
    </div>
  );

  if (vista === "barras") {
    return <BarrasComparadas dominios={dominios} onSeleccionar={onSeleccionar} extraAcciones={selector} />;
  }
  return (
    <>
      <div className="solo-amplio">
        <RadarMadurez dominios={dominios} onSeleccionar={onSeleccionar} extraAcciones={selector} />
      </div>
      <div className="solo-angosto">
        <BarrasComparadas dominios={dominios} onSeleccionar={onSeleccionar} />
      </div>
    </>
  );
}
