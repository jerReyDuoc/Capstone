"use client";

import { BadgeSeveridad } from "@/components/ui/Basicos";
import { IMPACTO_TEXTO, MATRIZ_SEVERIDAD, SEVERIDAD_TONO, type ImpactoConocido } from "@/lib/severidad";
import type { BrechaVista, EstadoBrecha } from "@/lib/types";

const IMPACTOS: ImpactoConocido[] = ["Alta", "Media", "Baja"];
const ESTADOS: [EstadoBrecha, string][] = [
  ["no_cumplido", "No cumplido"],
  ["parcialmente_cumplido", "Parcial"],
];

/**
 * HU-11 · Hace visible el análisis automático: cuántas brechas cayeron en cada
 * combinación de impacto del control × estado, y qué severidad resulta.
 * Es una tabla real (no un dibujo): se lee igual con lector de pantalla.
 */
export function MatrizPriorizacion({ brechas }: { brechas: BrechaVista[] }) {
  const contar = (impacto: ImpactoConocido, estado: EstadoBrecha) =>
    brechas.filter((b) => b.criticidad === impacto && b.estado === estado).length;
  const sinClasificar = brechas.filter((b) => b.criticidad === "Sin clasificar").length;

  return (
    <section className="card" aria-labelledby="matriz-titulo" style={{ display: "grid", gap: 12, alignContent: "start" }}>
      <div>
        <h2 className="card-title" id="matriz-titulo">Cómo se prioriza</h2>
        <p className="card-sub">Impacto de cada brecha × qué tan incumplida está</p>
      </div>
      <table className="matriz">
        <caption className="sr-only">Brechas por impacto y estado de cumplimiento, con la severidad resultante</caption>
        <thead>
          <tr>
            <td aria-hidden="true" style={{ border: 0, background: "transparent" }} />
            {ESTADOS.map(([e, t]) => (
              <th key={e} scope="col">{t}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {IMPACTOS.map((impacto) => (
            <tr key={impacto}>
              <th scope="row">Impacto {IMPACTO_TEXTO[impacto]}</th>
              {ESTADOS.map(([estado]) => {
                const sev = MATRIZ_SEVERIDAD[impacto][estado];
                const n = contar(impacto, estado);
                return (
                  <td key={estado} className={`sev-${SEVERIDAD_TONO[sev]} ${n === 0 ? "vacia" : ""}`}>
                    <span className="matriz-celda">
                      <BadgeSeveridad severidad={sev} />
                      <span className="matriz-num">
                        {n}
                        <span className="sr-only"> {n === 1 ? "brecha" : "brechas"}</span>
                      </span>
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {sinClasificar > 0 ? (
        <p className="card-sub">
          {sinClasificar} {sinClasificar === 1 ? "brecha no tiene" : "brechas no tienen"} impacto en el catálogo: aparecen al final como “Sin clasificar”.
        </p>
      ) : null}
    </section>
  );
}
