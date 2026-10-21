"use client";

import { useRef, useState } from "react";
import { formatoDiferencia, formatoPuntaje, NIVELES } from "@/lib/madurez";
import type { DominioVista } from "@/lib/types";
import { ChartFrame, posicionEnContenedor, Tooltip, type TooltipState } from "./ChartFrame";

const W = 600;
const FILA = 64;
const M = { top: 16, right: 56, bottom: 40, left: 168 };

/**
 * Barras horizontales agrupadas: tu empresa vs. promedio de la industria
 * por dominio, con las bandas de nivel de madurez de fondo.
 */
export function BarrasDominio({
  dominios,
  onSeleccionar,
}: {
  dominios: DominioVista[];
  onSeleccionar?: (d: DominioVista) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<TooltipState>(null);
  const hayIndustria = dominios.some((d) => d.promedioIndustria != null);

  const H = M.top + M.bottom + FILA * dominios.length;
  const iw = W - M.left - M.right;
  const x = (v: number) => M.left + (Math.max(0, Math.min(100, v)) / 100) * iw;
  const bandas = [
    { desde: 0, hasta: 25, n: "inicial" as const },
    { desde: 25, hasta: 50, n: "en_desarrollo" as const },
    { desde: 50, hasta: 75, n: "gestionado" as const },
    { desde: 75, hasta: 100, n: "optimizado" as const },
  ];

  const bajo = dominios.filter((d) => d.diferencia != null && d.diferencia < 0);
  const resumen = !hayIndustria
    ? "Aún no hay benchmark del rubro para comparar."
    : bajo.length === 0
      ? "Todos los dominios están sobre el promedio de la industria."
      : `${bajo.length} de ${dominios.length} dominios bajo el promedio de la industria: ${bajo.map((d) => d.nombre).join(", ")}.`;

  const tabla = (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Puntaje por dominio frente a la industria</caption>
        <thead>
          <tr>
            <th scope="col">Dominio</th>
            <th scope="col" className="num">Tu empresa</th>
            <th scope="col" className="num">Industria</th>
            <th scope="col">Comparación</th>
          </tr>
        </thead>
        <tbody>
          {dominios.map((d) => (
            <tr key={d.nombre}>
              <th scope="row">{d.nombre}</th>
              <td className="num">{formatoPuntaje(d.puntaje)}</td>
              <td className="num">{formatoPuntaje(d.promedioIndustria)}</td>
              <td>{formatoDiferencia(d.diferencia)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <ChartFrame
      titulo="Comparativa con la industria"
      subtitulo="Barra sólida: tu empresa · barra punteada: promedio del rubro"
      resumen={resumen}
      tabla={tabla}
    >
      <svg
        ref={svgRef}
        className="chart-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="group"
        aria-label="Barras horizontales por dominio"
        onMouseLeave={() => setTip(null)}
      >
        {bandas.map((b, i) => (
          <g key={b.n} aria-hidden="true">
            <rect
              x={x(b.desde)}
              y={M.top}
              width={x(b.hasta) - x(b.desde)}
              height={H - M.top - M.bottom}
              fill={i % 2 ? "rgba(255,255,255,0.018)" : "transparent"}
            />
            <text className="tick" x={(x(b.desde) + x(b.hasta)) / 2} y={H - 10} textAnchor="middle">
              {NIVELES[b.n].etiqueta}
            </text>
          </g>
        ))}
        {[0, 25, 50, 75, 100].map((t) => (
          <g key={t} aria-hidden="true">
            <line x1={x(t)} x2={x(t)} y1={M.top} y2={H - M.bottom} stroke="var(--grid)" />
            <text className="tick" x={x(t)} y={H - M.bottom + 14} textAnchor="middle">{t}</text>
          </g>
        ))}

        {dominios.map((d, i) => {
          const y0 = M.top + i * FILA + 12;
          const mostrar = () => {
            const p = posicionEnContenedor(svgRef.current, x(d.puntaje), y0);
            setTip({
              ...p,
              titulo: d.nombre,
              filas: [
                ["Tu empresa", formatoPuntaje(d.puntaje)],
                ["Industria", formatoPuntaje(d.promedioIndustria)],
                ["Controles", String(d.controles)],
              ],
            });
          };
          return (
            <g
              key={d.nombre}
              className="bar"
              tabIndex={0}
              role={onSeleccionar ? "button" : "img"}
              aria-label={`${d.nombre}: tu empresa ${formatoPuntaje(d.puntaje)}, industria ${formatoPuntaje(d.promedioIndustria)}. ${formatoDiferencia(d.diferencia)}.`}
              onMouseEnter={mostrar}
              onFocus={mostrar}
              onBlur={() => setTip(null)}
              onClick={() => onSeleccionar?.(d)}
              onKeyDown={(e) => {
                if (onSeleccionar && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  onSeleccionar(d);
                }
                if (e.key === "Escape") setTip(null);
              }}
            >
              <rect x={0} y={y0 - 8} width={W} height={FILA - 4} fill="transparent" />
              <text className="axis-label" x={M.left - 16} y={y0 + 10} textAnchor="end" dominantBaseline="middle" aria-hidden="true">
                {d.nombre}
              </text>
              <rect className="fill" x={M.left} y={y0} width={x(d.puntaje) - M.left} height={18} rx={5} fill="var(--accent-strong)" />
              <rect className="focus" x={M.left - 4} y={y0 - 4} width={x(d.puntaje) - M.left + 8} height={26} rx={8} fill="none" />
              <text className="value-label" x={x(d.puntaje) + 8} y={y0 + 10} dominantBaseline="middle" aria-hidden="true">
                {formatoPuntaje(d.puntaje)}
              </text>
              {d.promedioIndustria != null ? (
                <>
                  <rect
                    x={M.left}
                    y={y0 + 24}
                    width={x(d.promedioIndustria) - M.left}
                    height={10}
                    rx={4}
                    fill="rgba(143,163,255,0.12)"
                    stroke="var(--serie-industria)"
                    strokeWidth={1.5}
                    strokeDasharray="5 4"
                  />
                  <text x={x(d.promedioIndustria) + 8} y={y0 + 30} dominantBaseline="middle" style={{ fill: "var(--serie-industria)", fontSize: 11 }} aria-hidden="true">
                    {formatoPuntaje(d.promedioIndustria)}
                  </text>
                </>
              ) : null}
            </g>
          );
        })}
      </svg>
      {tip ? <Tooltip {...tip} /> : null}
    </ChartFrame>
  );
}
