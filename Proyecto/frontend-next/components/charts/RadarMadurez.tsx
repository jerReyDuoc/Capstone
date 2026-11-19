"use client";

/**
 * Radar de madurez por dimensión (Diagnóstico).
 *
 * Un eje por dimensión real de la evaluación (las que devuelve el resumen del backend: con las 4
 * del modelo la figura es un rombo). Series: tu empresa (relleno con degradado), la meta de
 * cumplimiento (línea de trazos) y el promedio del rubro (línea punteada, solo si la cohorte del
 * sector es suficiente en esa dimensión).
 *
 * Accesibilidad, igual que las barras: resumen en texto, "Ver como tabla", series que se pueden
 * ocultar y cada vértice enfocable con el teclado (tooltip al enfocarlo; Enter abre el detalle).
 * La animación de entrada se desactiva con "reducir movimiento".
 *
 * En pantallas angostas (< 600 px) el Diagnóstico muestra las barras en su lugar (MadurezPorDominio).
 */
import { useId, useRef, useState, type ReactNode } from "react";
import { formatoDiferenciaMeta, formatoPuntaje, NIVELES } from "@/lib/madurez";
import { anclaEtiqueta, anguloEje, limitar, partirEtiqueta, poligonoRadar, puntoEnEje } from "@/lib/radar";
import type { DominioVista } from "@/lib/types";
import { resumenBarrasComparadas, TablaMadurez } from "./BarrasComparadas";
import { ChartFrame, posicionEnContenedor, Tooltip, type TooltipState } from "./ChartFrame";

type Serie = "empresa" | "industria" | "meta";

const ANCHO = 560;
const ALTO = 464;
const CX = ANCHO / 2;
const CY = 228;
const RADIO = 150;
const ANILLOS = [25, 50, 75, 100];

export function RadarMadurez({
  dominios,
  onSeleccionar,
  extraAcciones,
}: {
  dominios: DominioVista[];
  onSeleccionar?: (d: DominioVista) => void;
  extraAcciones?: ReactNode;
}) {
  const uid = useId().replace(/:/g, "");
  const svg = useRef<SVGSVGElement>(null);
  const [tip, setTip] = useState<TooltipState>(null);
  const [activo, setActivo] = useState<number | null>(null);
  const [visibles, setVisibles] = useState<Record<Serie, boolean>>({ empresa: true, industria: true, meta: true });
  const alternar = (s: Serie) => setVisibles((v) => ({ ...v, [s]: !v[s] }));

  const n = dominios.length;
  const meta = dominios[0]?.meta ?? 75;
  const conRubro = dominios.filter((d) => d.promedioIndustria != null).length;
  const rubroCompleto = conRubro === n && n > 0;

  const etiqueta = (d: DominioVista) =>
    `${d.nombre}: tu empresa ${formatoPuntaje(d.puntaje)} de 100, nivel ${NIVELES[d.nivel].etiqueta}. ${formatoDiferenciaMeta(d.diferenciaMeta)}.${
      d.promedioIndustria != null ? ` Promedio del rubro ${formatoPuntaje(d.promedioIndustria)}.` : ""
    }${onSeleccionar ? " Presiona Enter para ver el detalle." : ""}`;

  const mostrar = (i: number) => {
    const d = dominios[i];
    const p = puntoEnEje(CX, CY, RADIO, d.puntaje, i, n);
    const pos = posicionEnContenedor(svg.current, p.x, p.y);
    const filas: [string, string][] = [
      ["Tu empresa", formatoPuntaje(d.puntaje)],
      ["Nivel", NIVELES[d.nivel].etiqueta],
      ["Meta", formatoPuntaje(d.meta)],
    ];
    if (d.promedioIndustria != null) filas.push(["Rubro", formatoPuntaje(d.promedioIndustria)]);
    setActivo(i);
    setTip({ x: pos.x, y: pos.y - 14, titulo: d.nombre, filas });
  };
  const ocultar = () => {
    setActivo(null);
    setTip(null);
  };

  const leyenda = (
    <div className="chart-acciones">
      {extraAcciones}
      <div className="chip-group" role="group" aria-label="Series visibles">
        <button type="button" className="chip" aria-pressed={visibles.empresa} onClick={() => alternar("empresa")}>
          <span className="chip-swatch radar-muestra-empresa" />
          Tu empresa
        </button>
        {conRubro ? (
          <button type="button" className="chip" aria-pressed={visibles.industria} onClick={() => alternar("industria")}>
            <span className="chip-swatch radar-muestra-rubro" />
            Promedio del rubro
          </button>
        ) : null}
        <button type="button" className="chip" aria-pressed={visibles.meta} onClick={() => alternar("meta")}>
          <span className="chip-swatch radar-muestra-meta" />
          Meta ({formatoPuntaje(meta)})
        </button>
      </div>
    </div>
  );

  const valoresEmpresa = dominios.map((d) => d.puntaje);
  const valoresMeta = dominios.map((d) => d.meta);

  return (
    <ChartFrame
      titulo="Madurez por dimensión"
      subtitulo="Puntaje 0–100 en cada dimensión evaluada. Mientras más amplia la figura, más madura tu empresa."
      resumen={resumenBarrasComparadas(dominios)}
      acciones={leyenda}
      tabla={<TablaMadurez dominios={dominios} />}
      pie={
        conRubro && !rubroCompleto ? (
          <span className="card-sub">El promedio del rubro solo se muestra en las dimensiones con suficientes empresas.</span>
        ) : null
      }
    >
      <svg
        ref={svg}
        className="radar"
        viewBox={`0 0 ${ANCHO} ${ALTO}`}
        role="group"
        aria-label="Radar de madurez por dimensión"
        onMouseLeave={ocultar}
      >
        <defs>
          <radialGradient id={`${uid}-relleno`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" className="radar-stop-centro" />
            <stop offset="100%" className="radar-stop-borde" />
          </radialGradient>
          <linearGradient id={`${uid}-trazo`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" className="radar-stop-trazo-a" />
            <stop offset="100%" className="radar-stop-trazo-b" />
          </linearGradient>
        </defs>

        {/* Rejilla: anillos suaves y ejes */}
        <g aria-hidden="true">
          {ANILLOS.map((a) => (
            <polygon
              key={a}
              className={a === 100 ? "radar-anillo radar-anillo-borde" : "radar-anillo"}
              points={poligonoRadar(dominios.map(() => a), CX, CY, RADIO)}
            />
          ))}
          {dominios.map((d, i) => {
            const p = puntoEnEje(CX, CY, RADIO, 100, i, n);
            return <line key={d.nombre} className="radar-eje" x1={CX} y1={CY} x2={p.x} y2={p.y} />;
          })}
          {ANILLOS.map((a) => (
            <text key={a} className="radar-escala" x={CX - 9} y={CY - (a / 100) * RADIO + 13} textAnchor="end">
              {a}
            </text>
          ))}
        </g>

        {/* Meta (trazos) */}
        {visibles.meta ? (
          <polygon className="radar-meta radar-entrada" style={{ transformOrigin: `${CX}px ${CY}px` }}
                   points={poligonoRadar(valoresMeta, CX, CY, RADIO)} aria-hidden="true" />
        ) : null}

        {/* Promedio del rubro (punteado): polígono si hay dato en todas; si no, solo marcas */}
        {visibles.industria && conRubro ? (
          <g aria-hidden="true" className="radar-entrada" style={{ transformOrigin: `${CX}px ${CY}px` }}>
            {rubroCompleto ? (
              <polygon className="radar-rubro" points={poligonoRadar(dominios.map((d) => d.promedioIndustria ?? 0), CX, CY, RADIO)} />
            ) : null}
            {dominios.map((d, i) => {
              if (d.promedioIndustria == null) return null;
              const p = puntoEnEje(CX, CY, RADIO, d.promedioIndustria, i, n);
              return <rect key={d.nombre} className="radar-rubro-marca" x={p.x - 4} y={p.y - 4} width={8} height={8}
                           transform={`rotate(45 ${p.x} ${p.y})`} />;
            })}
          </g>
        ) : null}

        {/* Tu empresa: relleno con degradado, trazo y vértices */}
        {visibles.empresa ? (
          <g className="radar-entrada" style={{ transformOrigin: `${CX}px ${CY}px` }}>
            <polygon className="radar-empresa" points={poligonoRadar(valoresEmpresa, CX, CY, RADIO)}
                     fill={`url(#${uid}-relleno)`} stroke={`url(#${uid}-trazo)`} aria-hidden="true" />
          </g>
        ) : null}

        {/* Etiquetas de los ejes: nombre y puntaje */}
        <g aria-hidden="true">
          {dominios.map((d, i) => {
            const a = anguloEje(i, n);
            const r = RADIO + 24;
            const x = CX + r * Math.cos(a);
            const lineas = partirEtiqueta(d.nombre);
            const alto = (lineas.length + 1) * 16;
            const sen = Math.sin(a);
            // Arriba: el bloque termina en el borde; abajo: empieza; a los lados: centrado
            const y0 = sen < -0.3 ? CY + r * sen - alto + 12 : sen > 0.3 ? CY + r * sen + 12 : CY + r * sen - alto / 2 + 12;
            const ancla = anclaEtiqueta(i, n);
            return (
              <text key={d.nombre} className={activo === i ? "radar-etiqueta radar-etiqueta-activa" : "radar-etiqueta"}
                    x={x} y={y0} textAnchor={ancla}>
                {lineas.map((l, j) => (
                  <tspan key={j} x={x} dy={j === 0 ? 0 : 16}>{l}</tspan>
                ))}
                <tspan x={x} dy={16} className="radar-etiqueta-valor">{formatoPuntaje(d.puntaje)}</tspan>
              </text>
            );
          })}
        </g>

        {/* Vértices: enfocables con teclado, tooltip con mouse y foco */}
        {visibles.empresa
          ? dominios.map((d, i) => {
              const p = puntoEnEje(CX, CY, RADIO, limitar(d.puntaje), i, n);
              return (
                <g
                  key={d.nombre}
                  className={`radar-vertice${activo === i ? " radar-vertice-activo" : ""}${onSeleccionar ? " radar-vertice-accion" : ""}`}
                  tabIndex={0}
                  role={onSeleccionar ? "button" : "img"}
                  aria-label={etiqueta(d)}
                  onMouseEnter={() => mostrar(i)}
                  onFocus={() => mostrar(i)}
                  onBlur={ocultar}
                  onClick={() => onSeleccionar?.(d)}
                  onKeyDown={(e) => {
                    if (!onSeleccionar) return;
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSeleccionar(d);
                    }
                  }}
                >
                  <circle className="radar-vertice-zona" cx={p.x} cy={p.y} r={16} />
                  <circle className="radar-vertice-punto" cx={p.x} cy={p.y} r={5.5} />
                </g>
              );
            })
          : null}
      </svg>
      {tip ? <Tooltip {...tip} /> : null}
    </ChartFrame>
  );
}
