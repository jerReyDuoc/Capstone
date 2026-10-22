"use client";

import Link from "next/link";
import { useEffect } from "react";
import { BarrasDominio } from "@/components/charts/BarrasDominio";
import { PageHeader } from "@/components/shell/PageHeader";
import { BadgeNivel, EstadoPanel } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { notaIndustria } from "@/lib/adaptadores";
import { formatoDiferencia, formatoDiferenciaMeta, formatoPuntaje, NIVELES } from "@/lib/madurez";
import { slug } from "@/lib/slug";

export function VistaDominios() {
  const { href, estado } = usePanel();

  // Al llegar desde el radar (…/dominios#gestion-de-riesgos) llevamos el foco a la tarjeta.
  useEffect(() => {
    if (estado.tipo !== "listo" || !window.location.hash) return;
    const el = document.getElementById(window.location.hash.slice(1));
    el?.scrollIntoView({ block: "start" });
    el?.focus({ preventScroll: true });
  }, [estado.tipo]);

  return (
    <>
      <PageHeader
        eyebrow="Madurez por dominio"
        titulo="Dominios"
        subtitulo="Detalle de cada dominio de gobernanza de IA: puntaje, nivel alcanzado, distancia a la meta, comparación con tu rubro y brechas abiertas."
      />

      <EstadoPanel>
        {(p) => (
          <>
            <div className="card">
              <BarrasDominio dominios={p.dominios} notaIndustria={notaIndustria(p) ?? undefined} />
            </div>

            <div className="grid">
              {p.dominios.map((d) => {
                const brechas = p.brechas.filter((b) => b.dominio === d.nombre);
                const altas = brechas.filter((b) => b.criticidad === "Alta").length;
                const id = slug(d.nombre);
                return (
                  <article key={d.nombre} id={id} tabIndex={-1} className="card col-6" aria-labelledby={`${id}-t`} style={{ display: "grid", gap: 16, scrollMarginTop: 24 }}>
                    <div className="card-head" style={{ marginBottom: 0 }}>
                      <div>
                        <h2 className="card-title" id={`${id}-t`}>{d.nombre}</h2>
                        <p className="card-sub">{d.controles} controles evaluados</p>
                      </div>
                      <BadgeNivel nivel={d.nivel} />
                    </div>

                    <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
                      <p className="kpi-value">
                        {formatoPuntaje(d.puntaje)}
                        <small>/ 100</small>
                      </p>
                      <p className="card-sub" style={{ color: d.diferenciaMeta < 0 ? "var(--alto)" : "var(--bajo)", fontWeight: 600 }}>
                        {formatoDiferenciaMeta(d.diferenciaMeta)}
                      </p>
                      {d.promedioIndustria != null ? (
                        <p className="card-sub">{formatoDiferencia(d.diferencia)} del rubro</p>
                      ) : null}
                    </div>

                    <div
                      className="domain-bar"
                      role="meter"
                      aria-label={`Puntaje de ${d.nombre}`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(d.puntaje)}
                      aria-valuetext={`${formatoPuntaje(d.puntaje)} de 100; meta ${formatoPuntaje(d.meta)}${d.promedioIndustria != null ? `; rubro ${formatoPuntaje(d.promedioIndustria)}` : ""}`}
                    >
                      <span className="fill" style={{ width: `${d.puntaje}%` }} />
                      <span className="mark mark-meta" style={{ left: `calc(${d.meta}% - 1px)` }} title={`Meta ${formatoPuntaje(d.meta)}`} />
                      {d.promedioIndustria != null ? (
                        <span className="mark" style={{ left: `calc(${d.promedioIndustria}% - 1px)` }} title="Promedio del rubro" />
                      ) : null}
                    </div>

                    <p className="card-sub">{NIVELES[d.nivel].descripcion}</p>

                    <div className="chart-foot">
                      <span>
                        {brechas.length === 0 ? (
                          "Sin brechas abiertas"
                        ) : (
                          <>
                            <strong style={{ color: "var(--text)" }}>{brechas.length}</strong> {brechas.length === 1 ? "brecha abierta" : "brechas abiertas"}
                            {altas ? (
                              <>
                                {" · "}
                                <strong style={{ color: "var(--alto)" }}>{altas}</strong> alta{altas > 1 ? "s" : ""}
                              </>
                            ) : null}
                          </>
                        )}
                      </span>
                      {brechas.length > 0 ? (
                        <Link href={href("/panel/brechas", { dominio: d.nombre })} className="btn btn-ghost btn-sm">
                          Ver brechas<span className="sr-only"> de {d.nombre}</span>
                          <Icon name="flecha" />
                        </Link>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          </>
        )}
      </EstadoPanel>
    </>
  );
}
