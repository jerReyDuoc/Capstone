"use client";

import { useRef, useState } from "react";
import { pluralSeveridad, SEVERIDAD_TONO, SEVERIDADES } from "@/lib/severidad";
import type { Severidad } from "@/lib/types";
import { ChartFrame, posicionEnContenedor, Tooltip, type TooltipState } from "./ChartFrame";

const W = 340;
const H = 280;
const M = { top: 28, right: 8, bottom: 40, left: 28 };

/**
 * Barras verticales: brechas abiertas por severidad (HU-11: Crítica, Alta, Media, Baja).
 * Cada barra es un botón: abre el listado filtrado por esa severidad.
 * (El archivo conserva su nombre de la HU-13 para no romper importaciones.)
 */
export function BarrasCriticidad({
  conteo,
  onSeleccionar,
}: {
  conteo: Record<Severidad, number>;
  onSeleccionar?: (s: Severidad) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<TooltipState>(null);

  // "Sin clasificar" solo aparece si existe al menos una.
  const categorias = SEVERIDADES.filter((c) => c !== "Sin clasificar" || conteo[c] > 0);
  const total = categorias.reduce((s, c) => s + conteo[c], 0);
  const max = Math.max(1, ...categorias.map((c) => conteo[c]));
  const tope = Math.max(4, Math.ceil(max / 2) * 2); // eje redondeado a número par
  const ticks = [0, tope / 2, tope];

  const iw = W - M.left - M.right;
  const ih = H - M.top - M.bottom;
  const banda = iw / categorias.length;
  const ancho = Math.min(56, banda * 0.56);
  const y = (v: number) => M.top + ih - (v / tope) * ih;

  const pct = (v: number) => (total ? Math.round((v / total) * 100) : 0);
  const resumen =
    total === 0
      ? "No hay brechas abiertas en esta evaluación."
      : `${total} brechas abiertas: ${categorias.map((c) => `${conteo[c]} ${pluralSeveridad(c, conteo[c])}`).join(", ")}.`;

  const tabla = (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Brechas abiertas por severidad</caption>
        <thead>
          <tr>
            <th scope="col">Severidad</th>
            <th scope="col" className="num">Brechas</th>
            <th scope="col" className="num">% del total</th>
          </tr>
        </thead>
        <tbody>
          {categorias.map((c) => (
            <tr key={c}>
              <th scope="row">{c}</th>
              <td className="num">{conteo[c]}</td>
              <td className="num">{pct(conteo[c])} %</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <ChartFrame
      titulo="Brechas por severidad"
      subtitulo="Impacto del control × estado de cumplimiento"
      resumen={resumen}
      tabla={tabla}
    >
      <svg
        ref={svgRef}
        className="chart-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="group"
        aria-label="Gráfico de barras de brechas por severidad"
        onMouseLeave={() => setTip(null)}
      >
        {ticks.map((t) => (
          <g key={t} aria-hidden="true">
            <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeDasharray={t === 0 ? undefined : "3 4"} />
            <text className="tick" x={M.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle">
              {t}
            </text>
          </g>
        ))}

        {categorias.map((c, i) => {
          const v = conteo[c];
          const x = M.left + banda * i + (banda - ancho) / 2;
          const h = Math.max(v > 0 ? 3 : 0, (v / tope) * ih);
          const tono = SEVERIDAD_TONO[c];
          const accionable = Boolean(onSeleccionar) && v > 0;
          const mostrar = () => {
            const p = posicionEnContenedor(svgRef.current, x + ancho / 2, y(v));
            setTip({ ...p, titulo: `Severidad ${c.toLowerCase()}`, filas: [["Brechas", String(v)], ["% del total", `${pct(v)} %`]] });
          };
          return (
            <g
              key={c}
              className="bar"
              tabIndex={0}
              role={accionable ? "button" : "img"}
              aria-disabled={onSeleccionar && !accionable ? true : undefined}
              aria-label={`Severidad ${c}: ${v} brechas, ${pct(v)} % del total.${accionable ? " Presiona Enter para ver el listado." : ""}`}
              onMouseEnter={mostrar}
              onFocus={mostrar}
              onBlur={() => setTip(null)}
              onClick={() => accionable && onSeleccionar?.(c)}
              onKeyDown={(e) => {
                if (accionable && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  onSeleccionar?.(c);
                }
                if (e.key === "Escape") setTip(null);
              }}
            >
              {/* zona de impacto: toda la banda */}
              <rect x={M.left + banda * i} y={M.top} width={banda} height={ih} fill="transparent" />
              <rect className="fill" x={x} y={y(v)} width={ancho} height={h} rx={6} fill={`var(--${tono})`} />
              <rect className="focus" x={x - 4} y={y(v) - 4} width={ancho + 8} height={h + 8} rx={9} fill="none" />
              <text className="value-label" x={x + ancho / 2} y={y(v) - 10} textAnchor="middle" aria-hidden="true">
                {v}
              </text>
              <text className="axis-label" x={x + ancho / 2} y={H - M.bottom + 22} textAnchor="middle" aria-hidden="true">
                {c === "Sin clasificar" ? "S/C" : c}
              </text>
            </g>
          );
        })}
      </svg>
      {tip ? <Tooltip {...tip} /> : null}
    </ChartFrame>
  );
}
