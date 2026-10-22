"use client";

import { Icon } from "@/components/ui/Icon";
import { SEVERIDAD_GUIA, SEVERIDAD_TONO, SEVERIDADES_PRINCIPALES, pluralSeveridad } from "@/lib/severidad";
import type { Severidad } from "@/lib/types";

/**
 * HU-11 · Las cuatro severidades del criterio de aceptación, como tarjetas que
 * también filtran (botones conmutables, admiten varias a la vez).
 */
export function TarjetasSeveridad({
  conteo,
  seleccion,
  onAlternar,
}: {
  conteo: Record<Severidad, number>;
  seleccion: Severidad[];
  onAlternar: (s: Severidad) => void;
}) {
  return (
    <div className="sev-tiles" role="group" aria-label="Filtrar por severidad">
      {SEVERIDADES_PRINCIPALES.map((s) => {
        const n = conteo[s];
        const activa = seleccion.includes(s);
        return (
          <button
            key={s}
            type="button"
            className={`sev-tile sev-${SEVERIDAD_TONO[s]}`}
            aria-pressed={activa}
            // Una severidad sin brechas no filtra nada útil, salvo que ya esté activa (para poder quitarla).
            disabled={n === 0 && !activa}
            aria-label={`${s}: ${n} ${n === 1 ? "brecha" : "brechas"}. ${SEVERIDAD_GUIA[s]}.`}
            onClick={() => onAlternar(s)}
          >
            <span className="sev-tile-top">
              <span className="sev-tile-nombre">{s}</span>
              <Icon name="check" className="sev-tile-check" />
            </span>
            <span className="sev-tile-valor">
              {n}
              <span className="sr-only"> {pluralSeveridad(s, n)}</span>
            </span>
            <span className="sev-tile-guia">{SEVERIDAD_GUIA[s]}</span>
          </button>
        );
      })}
    </div>
  );
}
