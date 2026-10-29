"use client";

import { useId, useState, type ReactNode } from "react";

/**
 * Envoltorio común de gráficos:
 * - <figure> + <figcaption> con el resumen en texto (WCAG 1.1.1).
 * - Alternativa en tabla de datos accesible por teclado (WCAG 1.3.1).
 */
export function ChartFrame({
  titulo,
  subtitulo,
  resumen,
  acciones,
  tabla,
  children,
  pie,
  resumenVisible = true,
}: {
  titulo: string;
  subtitulo?: string;
  /** Lectura en una frase de lo que muestra el gráfico. */
  resumen: string;
  acciones?: ReactNode;
  tabla: ReactNode;
  children: ReactNode;
  pie?: ReactNode;
  /**
   * Correcciones 29-10: con false el resumen deja de verse bajo el gráfico, pero sigue siendo su
   * descripción para lectores de pantalla (aria-describedby, WCAG 1.1.1).
   */
  resumenVisible?: boolean;
}) {
  const [verTabla, setVerTabla] = useState(false);
  const idTitulo = useId();
  const idResumen = useId();
  const idTabla = useId();

  return (
    <figure className="chart" aria-labelledby={idTitulo} aria-describedby={idResumen}>
      <div className="card-head" style={{ marginBottom: 0 }}>
        <div>
          <h2 className="card-title" id={idTitulo}>{titulo}</h2>
          {subtitulo ? <p className="card-sub">{subtitulo}</p> : null}
        </div>
        {acciones}
      </div>

      {verTabla ? <div id={idTabla}>{tabla}</div> : <div className="chart-wrap">{children}</div>}

      <figcaption className={resumenVisible ? "chart-foot" : "chart-foot chart-foot-solo"}>
        <span id={idResumen} className={resumenVisible ? undefined : "sr-only"}>{resumen}</span>
        <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {pie}
          <button
            type="button"
            className="link-btn"
            aria-pressed={verTabla}
            aria-controls={verTabla ? idTabla : undefined}
            onClick={() => setVerTabla((v) => !v)}
          >
            {verTabla ? "Ver gráfico" : "Ver como tabla"}
          </button>
        </span>
      </figcaption>
    </figure>
  );
}

/** Tooltip flotante; su contenido también está en el aria-label del elemento enfocado. */
export function Tooltip({
  x,
  y,
  titulo,
  filas,
}: {
  x: number;
  y: number;
  titulo: string;
  filas: [string, string][];
}) {
  return (
    <div className="tooltip" style={{ left: x, top: y }} aria-hidden="true">
      <div className="tooltip-title">{titulo}</div>
      {filas.map(([k, v]) => (
        <div className="tooltip-row" key={k}>
          <span>{k}</span>
          <strong>{v}</strong>
        </div>
      ))}
    </div>
  );
}

export type TooltipState = { x: number; y: number; titulo: string; filas: [string, string][] } | null;

/**
 * Convierte coordenadas del viewBox del SVG a píxeles del contenedor, para
 * ubicar el tooltip encima del punto aunque el SVG esté escalado.
 */
export function posicionEnContenedor(svg: SVGSVGElement | null, vx: number, vy: number) {
  if (!svg) return { x: vx, y: vy };
  const vb = svg.viewBox.baseVal;
  const r = svg.getBoundingClientRect();
  const parent = svg.parentElement?.getBoundingClientRect() ?? r;
  return {
    x: r.left - parent.left + (vx / vb.width) * r.width,
    y: r.top - parent.top + (vy / vb.height) * r.height,
  };
}
