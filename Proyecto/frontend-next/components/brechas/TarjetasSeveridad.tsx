"use client";

import { SEVERIDAD_FORMA, SEVERIDAD_GUIA, SEVERIDAD_TONO, SEVERIDADES_PRINCIPALES, pluralSeveridad } from "@/lib/severidad";
import type { Severidad } from "@/lib/types";

/**
 * HU-11 · Las cuatro severidades, que también filtran el listado (botones conmutables, admiten
 * varias a la vez).
 *
 * Auditoría UX 16-11 · Fase 5.B: antes eran cuatro tarjetas grandes y el mismo conteo se repetía
 * en la matriz y en el listado. Ahora es UN resumen compacto: una fila de chips con color y forma
 * propios por severidad, que deja la tabla visible sin desplazar.
 */
export function ChipsSeveridad({
  conteo,
  seleccion,
  onAlternar,
}: {
  conteo: Record<Severidad, number>;
  seleccion: Severidad[];
  onAlternar: (s: Severidad) => void;
}) {
  return (
    <div className="chips-severidad" role="group" aria-label="Resumen por severidad (también filtra el listado)">
      {SEVERIDADES_PRINCIPALES.map((s) => {
        const n = conteo[s];
        const activa = seleccion.includes(s);
        return (
          <button
            key={s}
            type="button"
            className={`chip chip-severidad sev-${SEVERIDAD_TONO[s]} sev-forma-${SEVERIDAD_FORMA[s]}`}
            aria-pressed={activa}
            // Una severidad sin brechas no filtra nada útil, salvo que ya esté activa (para poder quitarla).
            disabled={n === 0 && !activa}
            title={SEVERIDAD_GUIA[s]}
            aria-label={`${s}: ${n} ${n === 1 ? "brecha" : "brechas"}. ${SEVERIDAD_GUIA[s]}. ${activa ? "Filtro activo." : "Filtrar."}`}
            onClick={() => onAlternar(s)}
          >
            <span className="chip-severidad-nombre">{s}</span>
            <strong>
              {n}
              <span className="sr-only"> {pluralSeveridad(s, n)}</span>
            </strong>
          </button>
        );
      })}
    </div>
  );
}
