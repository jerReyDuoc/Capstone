"use client";

/**
 * Auditoría UX 16-11 · Fase 5.A: reemplaza al radar de 4 ejes.
 *
 * Barras horizontales por dominio con dos series comparables —tu empresa y el promedio del
 * rubro— sobre la misma escala 0–100, y la meta de cumplimiento como una marca vertical.
 * Las barras se leen mejor que un radar (largo sobre una base común) y caben en móvil.
 *
 * Se conserva todo lo accesible del radar: resumen en texto, "Ver como tabla", series que se
 * pueden ocultar, y cada dominio enfocable (Enter abre el detalle si hay `onSeleccionar`).
 * Las series se distinguen también por forma: la empresa es sólida y el rubro rayado.
 */
import { useState } from "react";
import { formatoDiferencia, formatoDiferenciaMeta, formatoPuntaje, NIVELES } from "@/lib/madurez";
import type { DominioVista } from "@/lib/types";
import { ChartFrame } from "./ChartFrame";

type Serie = "empresa" | "industria" | "meta";

const pct = (v: number | null | undefined) => `${Math.max(0, Math.min(100, v ?? 0))}%`;

export function resumenBarrasComparadas(dominios: DominioVista[]): string {
  const n = dominios.length;
  if (n === 0) return "Sin dominios evaluados.";
  const meta = dominios[0]?.meta ?? 75;
  const mejor = [...dominios].sort((a, b) => b.puntaje - a.puntaje)[0];
  const peor = [...dominios].sort((a, b) => a.puntaje - b.puntaje)[0];
  const bajoMeta = dominios.filter((d) => d.diferenciaMeta < 0).length;
  const conRubro = dominios.filter((d) => d.promedioIndustria != null);
  const sobreRubro = conRubro.filter((d) => (d.diferencia ?? 0) > 0).length;
  return `Mayor madurez en ${mejor.nombre} (${formatoPuntaje(mejor.puntaje)}) y menor en ${peor.nombre} (${formatoPuntaje(peor.puntaje)}), en escala de 0 a 100. ${
    bajoMeta === 0 ? `Todas las dimensiones alcanzan la meta de ${formatoPuntaje(meta)}.` : `${bajoMeta} de ${n} bajo la meta de ${formatoPuntaje(meta)}.`
  }${conRubro.length ? ` Sobre el promedio del rubro en ${sobreRubro} de ${conRubro.length}.` : ""}`;
}

export function BarrasComparadas({
  dominios,
  onSeleccionar,
  titulo = "Madurez por dominio",
  subtitulo,
}: {
  dominios: DominioVista[];
  onSeleccionar?: (d: DominioVista) => void;
  titulo?: string;
  subtitulo?: string;
}) {
  const hayIndustria = dominios.some((d) => d.promedioIndustria != null);
  const meta = dominios[0]?.meta ?? 75;
  const [visibles, setVisibles] = useState<Record<Serie, boolean>>({ empresa: true, industria: true, meta: true });
  const alternar = (s: Serie) => setVisibles((v) => ({ ...v, [s]: !v[s] }));

  const leyenda = (
    <div className="chip-group" role="group" aria-label="Series visibles">
      <button type="button" className="chip" aria-pressed={visibles.empresa} onClick={() => alternar("empresa")}>
        <span className="chip-swatch barra-muestra-empresa" />
        Tu empresa
      </button>
      {hayIndustria ? (
        <button type="button" className="chip" aria-pressed={visibles.industria} onClick={() => alternar("industria")}>
          <span className="chip-swatch barra-muestra-rubro" />
          Promedio del rubro
        </button>
      ) : null}
      <button type="button" className="chip" aria-pressed={visibles.meta} onClick={() => alternar("meta")}>
        <span className="chip-swatch barra-muestra-meta" />
        Meta ({formatoPuntaje(meta)})
      </button>
    </div>
  );

  const tabla = (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">Puntaje de madurez por dominio, comparado con el rubro y la meta</caption>
        <thead>
          <tr>
            <th scope="col">Dominio</th>
            <th scope="col" className="num">Tu empresa</th>
            <th scope="col">Nivel</th>
            <th scope="col" className="num">Meta</th>
            {hayIndustria ? <th scope="col" className="num">Rubro</th> : null}
            {hayIndustria ? <th scope="col" className="num">Diferencia</th> : null}
          </tr>
        </thead>
        <tbody>
          {dominios.map((d) => (
            <tr key={d.id}>
              <th scope="row">{d.nombre}</th>
              <td className="num">{formatoPuntaje(d.puntaje)}</td>
              <td>{NIVELES[d.nivel].etiqueta}</td>
              <td className="num">{formatoPuntaje(d.meta)}</td>
              {hayIndustria ? <td className="num">{formatoPuntaje(d.promedioIndustria)}</td> : null}
              {hayIndustria ? <td className="num">{d.diferencia != null ? `${d.diferencia > 0 ? "+" : ""}${formatoPuntaje(d.diferencia)}` : "—"}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const etiqueta = (d: DominioVista) =>
    `${d.nombre}: tu empresa ${formatoPuntaje(d.puntaje)} de 100, nivel ${NIVELES[d.nivel].etiqueta}. ${formatoDiferenciaMeta(d.diferenciaMeta)}.${
      d.promedioIndustria != null ? ` Rubro ${formatoPuntaje(d.promedioIndustria)}, ${formatoDiferencia(d.diferencia)}.` : ""
    }${onSeleccionar ? " Presiona Enter para ver el detalle." : ""}`;

  return (
    <ChartFrame
      titulo={titulo}
      subtitulo={subtitulo ?? (hayIndustria ? "Puntaje 0–100 de tu empresa frente al promedio del rubro y la meta" : "Puntaje 0–100 frente a la meta")}
      resumen={resumenBarrasComparadas(dominios)}
      acciones={leyenda}
      tabla={tabla}
    >
      <ul className="barras-comparadas">
        {dominios.map((d) => {
          const contenido = (
            <>
              <span className="bc-cabeza">
                <span className="bc-nombre">{d.nombre}</span>
                <span className="bc-valores">
                  {visibles.empresa ? <strong>{formatoPuntaje(d.puntaje)}</strong> : null}
                  {visibles.industria && d.promedioIndustria != null ? <span> · rubro {formatoPuntaje(d.promedioIndustria)}</span> : null}
                </span>
              </span>
              <span className="bc-pistas" aria-hidden="true">
                {visibles.empresa ? (
                  <span className="bc-pista">
                    <span className="bc-barra bc-empresa" style={{ width: pct(d.puntaje) }} />
                  </span>
                ) : null}
                {visibles.industria && d.promedioIndustria != null ? (
                  <span className="bc-pista">
                    <span className="bc-barra bc-rubro" style={{ width: pct(d.promedioIndustria) }} />
                  </span>
                ) : null}
                {visibles.meta ? <span className="bc-meta" style={{ left: pct(d.meta) }} /> : null}
              </span>
              <span className="bc-pie">{formatoDiferenciaMeta(d.diferenciaMeta)}</span>
            </>
          );
          return (
            <li key={d.id}>
              {onSeleccionar ? (
                <button type="button" className="bc-fila bc-fila-boton" aria-label={etiqueta(d)} onClick={() => onSeleccionar(d)}>
                  {contenido}
                </button>
              ) : (
                <div className="bc-fila" role="group" aria-label={etiqueta(d)}>
                  {contenido}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <p className="bc-escala" aria-hidden="true">
        <span>0</span>
        <span>50</span>
        <span>100</span>
      </p>
    </ChartFrame>
  );
}
