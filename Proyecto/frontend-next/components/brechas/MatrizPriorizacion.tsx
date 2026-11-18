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
export function MatrizPriorizacion({ brechas, plano = false }: { brechas: BrechaVista[]; /** Sin tarjeta propia (dentro de "¿Cómo se prioriza?"). */ plano?: boolean }) {
  const contar = (impacto: ImpactoConocido, estado: EstadoBrecha) =>
    brechas.filter((b) => b.criticidad === impacto && b.estado === estado).length;
  const sinClasificar = brechas.filter((b) => b.criticidad === "Sin clasificar").length;

  return (
    <section className={plano ? "pila-chica" : "card pila-chica"} aria-labelledby="matriz-titulo">
      <div>
        <h2 className={plano ? "sr-only" : "card-title"} id="matriz-titulo">Cómo se prioriza</h2>
        <p className="card-sub">La severidad cruza el impacto de cada brecha con qué tan incumplida está.</p>
      </div>
      {/* Auditoría UX 16-11: desplazamiento interno contenido (no empuja el ancho de la página) */}
      <div className="scroll-x" role="region" aria-label="Matriz de priorización" tabIndex={0}>
      <table className="matriz">
        <caption className="sr-only">Brechas por impacto y estado de cumplimiento, con la severidad resultante</caption>
        <thead>
          <tr>
            <td aria-hidden="true" className="matriz-esquina" />
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
      </div>
      {sinClasificar > 0 ? (
        <p className="card-sub">
          {sinClasificar} {sinClasificar === 1 ? "brecha no tiene" : "brechas no tienen"} impacto en el catálogo: aparecen al final como “Sin clasificar”.
        </p>
      ) : null}
    </section>
  );
}
