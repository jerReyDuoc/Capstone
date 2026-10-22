"use client";

import { useMemo, useRef, useState } from "react";
import { formatoDiferencia, formatoDiferenciaMeta, formatoPuntaje, NIVELES } from "@/lib/madurez";
import type { DominioVista } from "@/lib/types";
import { ChartFrame, posicionEnContenedor, Tooltip, type TooltipState } from "./ChartFrame";

const W = 520;
const H = 430;
const CX = W / 2;
const CY = H / 2 + 6;
const R = 168;
const ANILLOS = [25, 50, 75, 100];

type Serie = "empresa" | "industria" | "meta";

/**
 * Radar de madurez por dominio (0-100) con la META de cumplimiento (lo que debería
 * alcanzar cada dimensión) y, si hay muestras suficientes, el promedio del rubro. Interactivo: hover/foco muestra detalle, Enter abre el dominio,
 * las leyendas activan/desactivan cada serie.
 */
export function RadarMadurez({
  dominios,
  onSeleccionar,
}: {
  dominios: DominioVista[];
  onSeleccionar?: (d: DominioVista) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<TooltipState>(null);
  const hayIndustria = dominios.some((d) => d.promedioIndustria != null);
  const [visibles, setVisibles] = useState<Record<Serie, boolean>>({ empresa: true, industria: true, meta: true });
  const hayMeta = dominios.length > 0;
  const meta = dominios[0]?.meta ?? 75;
  const bajoMeta = dominios.filter((d) => d.diferenciaMeta < 0);

  const n = dominios.length;
  const angulo = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const punto = (i: number, valor: number) => {
    const r = (Math.max(0, Math.min(100, valor)) / 100) * R;
    return [CX + r * Math.cos(angulo(i)), CY + r * Math.sin(angulo(i))] as const;
  };

  const poligono = (valores: (number | null)[]) =>
    valores.map((v, i) => punto(i, v ?? 0).join(",")).join(" ");

  const empresa = useMemo(() => dominios.map((d) => d.puntaje), [dominios]);
  const industria = useMemo(() => dominios.map((d) => d.promedioIndustria), [dominios]);

  const mejor = [...dominios].sort((a, b) => b.puntaje - a.puntaje)[0];
  const peor = [...dominios].sort((a, b) => a.puntaje - b.puntaje)[0];
  const resumen =
    n === 0
      ? "Sin dominios evaluados."
      : `Mayor madurez en ${mejor.nombre} (${formatoPuntaje(mejor.puntaje)}) y menor en ${peor.nombre} (${formatoPuntaje(peor.puntaje)}), en escala de 0 a 100. ${
          bajoMeta.length === 0 ? `Todas las dimensiones alcanzan la meta de ${formatoPuntaje(meta)}.` : `${bajoMeta.length} de ${n} bajo la meta de ${formatoPuntaje(meta)}.`
        }`;

  const mostrar = (d: DominioVista, i: number, serie: Serie) => {
    const v = serie === "empresa" ? d.puntaje : serie === "meta" ? d.meta : d.promedioIndustria ?? 0;
    const [px, py] = punto(i, v);
    const { x, y } = posicionEnContenedor(svgRef.current, px, py);
    setTip({
      x,
      y,
      titulo: d.nombre,
      filas: [
        ["Tu empresa", formatoPuntaje(d.puntaje)],
        ["Nivel", NIVELES[d.nivel].etiqueta],
        ["Meta", `${formatoPuntaje(d.meta)} (${d.diferenciaMeta >= 0 ? "cumple" : `faltan ${formatoPuntaje(-d.diferenciaMeta)}`})`],
        ...(d.promedioIndustria != null
          ? ([
              ["Industria", formatoPuntaje(d.promedioIndustria)],
              ["Diferencia", d.diferencia != null ? `${d.diferencia > 0 ? "+" : ""}${formatoPuntaje(d.diferencia)}` : "—"],
            ] as [string, string][])
          : []),
      ],
    });
  };

  const etiquetaPunto = (d: DominioVista, serie: Serie) =>
    serie === "empresa"
      ? `${d.nombre}: tu empresa ${formatoPuntaje(d.puntaje)} de 100, nivel ${NIVELES[d.nivel].etiqueta}. ${formatoDiferenciaMeta(d.diferenciaMeta)}.${d.promedioIndustria != null ? ` Industria ${formatoPuntaje(d.promedioIndustria)}, ${formatoDiferencia(d.diferencia)}.` : ""}${onSeleccionar ? " Presiona Enter para ver el detalle." : ""}`
      : `${d.nombre}: promedio de la industria ${formatoPuntaje(d.promedioIndustria)} de 100.`;

  const leyenda = (
    <div className="chip-group" role="group" aria-label="Series visibles">
      <button
        type="button"
        className="chip"
        aria-pressed={visibles.empresa}
        onClick={() => setVisibles((v) => ({ ...v, empresa: !v.empresa }))}
      >
        <span className="chip-swatch" style={{ background: "var(--serie-empresa)" }} />
        Tu empresa
      </button>
      {hayMeta ? (
        <button
          type="button"
          className="chip"
          aria-pressed={visibles.meta}
          onClick={() => setVisibles((v) => ({ ...v, meta: !v.meta }))}
        >
          <span className="chip-swatch" style={{ background: "transparent", border: "2px dotted var(--serie-meta)" }} />
          Meta ({formatoPuntaje(meta)})
        </button>
      ) : null}
      {hayIndustria ? (
        <button
          type="button"
          className="chip"
          aria-pressed={visibles.industria}
          onClick={() => setVisibles((v) => ({ ...v, industria: !v.industria }))}
        >
          <span
            className="chip-swatch"
            style={{ background: "transparent", border: "2px dashed var(--serie-industria)" }}
          />
          Promedio industria
        </button>
      ) : null}
    </div>
  );

  const tabla = (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Puntaje de madurez por dominio</caption>
        <thead>
          <tr>
            <th scope="col">Dominio</th>
            <th scope="col" className="num">Tu empresa</th>
            <th scope="col">Nivel</th>
            <th scope="col" className="num">Meta</th>
            {hayIndustria ? <th scope="col" className="num">Industria</th> : null}
            {hayIndustria ? <th scope="col" className="num">Diferencia</th> : null}
          </tr>
        </thead>
        <tbody>
          {dominios.map((d) => (
            <tr key={d.nombre}>
              <th scope="row">{d.nombre}</th>
              <td className="num">{formatoPuntaje(d.puntaje)}</td>
              <td>{NIVELES[d.nivel].etiqueta}</td>
              <td className="num">{formatoPuntaje(d.meta)}</td>
              {hayIndustria ? <td className="num">{formatoPuntaje(d.promedioIndustria)}</td> : null}
              {hayIndustria ? (
                <td className="num">{d.diferencia != null ? `${d.diferencia > 0 ? "+" : ""}${formatoPuntaje(d.diferencia)}` : "—"}</td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <ChartFrame
      titulo="Madurez por dominio"
      subtitulo={hayIndustria ? "Puntaje 0–100 frente a la meta y al promedio de tu rubro" : "Puntaje 0–100 frente a la meta de cumplimiento"}
      resumen={resumen}
      acciones={leyenda}
      tabla={tabla}
    >
      {n < 3 ? (
        <p className="card-sub">Se necesitan al menos 3 dominios para dibujar el radar. Usa la vista de tabla.</p>
      ) : (
        <svg
          ref={svgRef}
          className="chart-svg"
          viewBox={`0 0 ${W} ${H}`}
          role="group"
          aria-label="Radar de madurez. Usa Tab para recorrer los dominios."
          onMouseLeave={() => setTip(null)}
        >
          {/* Anillos de referencia */}
          {ANILLOS.map((a) => (
            <polygon
              key={a}
              points={poligono(Array(n).fill(a))}
              fill={a === 100 ? "rgba(255,255,255,0.012)" : "none"}
              stroke="var(--grid)"
              strokeWidth={1}
            />
          ))}
          {/* Valores de los anillos sobre la bisectriz entre el 1.er y 2.º eje: no chocan con las etiquetas */}
          {ANILLOS.map((a) => {
            const ang = -Math.PI / 2 + Math.PI / n;
            const r = (a / 100) * R * Math.cos(Math.PI / n);
            return (
              <text key={`t${a}`} className="tick" x={CX + r * Math.cos(ang) + 4} y={CY + r * Math.sin(ang) - 4} aria-hidden="true">
                {a}
              </text>
            );
          })}
          {/* Ejes y etiquetas */}
          {dominios.map((d, i) => {
            const [x, y] = punto(i, 100);
            const [lx, ly] = punto(i, 116);
            const cos = Math.cos(angulo(i));
            const anchor = Math.abs(cos) < 0.2 ? "middle" : cos > 0 ? "start" : "end";
            // En el eje superior las dos líneas crecen hacia arriba para no pisar el gráfico
            const dy = Math.sin(angulo(i)) < -0.5 ? -18 : 0;
            return (
              <g key={d.nombre} aria-hidden="true">
                <line x1={CX} y1={CY} x2={x} y2={y} stroke="var(--grid)" />
                <text className="axis-label" x={lx} y={ly + dy} textAnchor={anchor} dominantBaseline="middle">
                  {d.nombre}
                </text>
                <text
                  x={lx}
                  y={ly + dy + 17}
                  textAnchor={anchor}
                  dominantBaseline="middle"
                  style={{ fill: `var(--${NIVELES[d.nivel].tono})`, fontSize: 13, fontWeight: 600 }}
                >
                  {formatoPuntaje(d.puntaje)} · {NIVELES[d.nivel].etiqueta}
                </text>
              </g>
            );
          })}

          {/* Meta de cumplimiento: anillo de puntos (forma distinta de la industria, WCAG 1.4.1) */}
          {hayMeta && visibles.meta ? (
            <polygon
              points={poligono(dominios.map((d) => d.meta))}
              fill="none"
              stroke="var(--serie-meta)"
              strokeWidth={2}
              strokeDasharray="1 6"
              strokeLinecap="round"
              aria-hidden="true"
            />
          ) : null}
          {/* Serie industria (punteada: no depende solo del color, WCAG 1.4.1) */}
          {hayIndustria && visibles.industria ? (
            <polygon
              points={poligono(industria)}
              fill="rgba(143,163,255,0.08)"
              stroke="var(--serie-industria)"
              strokeWidth={2}
              strokeDasharray="6 5"
              aria-hidden="true"
            />
          ) : null}
          {visibles.empresa ? (
            <polygon
              points={poligono(empresa)}
              fill="rgba(20,216,158,0.18)"
              stroke="var(--serie-empresa)"
              strokeWidth={2.5}
              strokeLinejoin="round"
              aria-hidden="true"
            />
          ) : null}

          {/* Puntos interactivos */}
          {(["industria", "empresa"] as Serie[]).map((serie) =>
            visibles[serie] && (serie === "empresa" || hayIndustria)
              ? dominios.map((d, i) => {
                  const v = serie === "empresa" ? d.puntaje : d.promedioIndustria;
                  if (v == null) return null;
                  const [x, y] = punto(i, v);
                  const color = serie === "empresa" ? "var(--serie-empresa)" : "var(--serie-industria)";
                  return (
                    <g
                      key={`${serie}-${d.nombre}`}
                      className="chart-point"
                      // Solo la serie de la empresa entra al orden de Tab; el dato de la
                      // industria ya se anuncia en su etiqueta y en la vista de tabla.
                      tabIndex={serie === "empresa" ? 0 : undefined}
                      role={serie === "empresa" ? (onSeleccionar ? "button" : "img") : undefined}
                      aria-label={serie === "empresa" ? etiquetaPunto(d, serie) : undefined}
                      aria-hidden={serie === "empresa" ? undefined : true}
                      onMouseEnter={() => mostrar(d, i, serie)}
                      onFocus={() => mostrar(d, i, serie)}
                      onBlur={() => setTip(null)}
                      onClick={() => serie === "empresa" && onSeleccionar?.(d)}
                      onKeyDown={(e) => {
                        if (serie === "empresa" && onSeleccionar && (e.key === "Enter" || e.key === " ")) {
                          e.preventDefault();
                          onSeleccionar(d);
                        }
                        if (e.key === "Escape") setTip(null);
                      }}
                    >
                      {/* área de impacto de 44px aprox. para tablets */}
                      <circle className="hit" cx={x} cy={y} r={18} />
                      <circle className="ring" cx={x} cy={y} r={serie === "empresa" ? 8 : 6} fill="var(--surface)" stroke={color} strokeWidth={2} />
                      {serie === "empresa" ? <circle className="dot" cx={x} cy={y} r={4} fill={color} /> : null}
                    </g>
                  );
                })
              : null,
          )}
        </svg>
      )}
      {tip ? <Tooltip {...tip} /> : null}
    </ChartFrame>
  );
}
