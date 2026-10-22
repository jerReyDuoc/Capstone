"use client";

import Link from "next/link";
import { BadgeSeveridad } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { useVistasFijadas } from "@/hooks/useVistasFijadas";
import { MAX_VISTAS } from "@/lib/vistasFijadas";
import { describirFiltros, filtrarBrechas, filtrosAParams } from "@/lib/filtrosBrechas";
import { contarPorSeveridad, pluralSeveridad, SEVERIDAD_TONO, SEVERIDADES } from "@/lib/severidad";
import type { PanelVista } from "@/lib/types";

/**
 * HU-11 · Listados de brechas que el gestor "exportó al dashboard" desde Brechas.
 * Los conteos se recalculan con los datos vigentes; si no hay vistas no se dibuja nada.
 */
export function VistasFijadas({ panel }: { panel: PanelVista }) {
  const { href } = usePanel();
  const { vistas, quitar } = useVistasFijadas(panel.evaluacionId);
  if (vistas.length === 0) return null;

  return (
    <section aria-labelledby="vistas-fijadas-titulo" style={{ display: "grid", gap: "var(--sp-4)" }}>
      <div className="card-head" style={{ marginBottom: 0 }}>
        <div>
          <h2 className="card-title" id="vistas-fijadas-titulo">Brechas en seguimiento</h2>
          <p className="card-sub">Listados fijados desde Brechas · se guardan en este navegador</p>
        </div>
      </div>
      <ul className="pin-grid" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {vistas.map((v) => {
          const lista = filtrarBrechas(panel.brechas, v.filtros);
          const conteo = contarPorSeveridad(lista);
          const niveles = SEVERIDADES.filter((s) => conteo[s] > 0);
          const titulo = describirFiltros(v.filtros);
          const top = lista[0];
          return (
            <li key={v.id} className="card pin-card">
              <div className="pin-head">
                <h3 className="pin-title">{titulo}</h3>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label={`Dejar de seguir “${titulo}”`}
                  onClick={() => quitar(v.id)}
                >
                  <Icon name="cerrar" />
                </button>
              </div>
              <p className="pin-total">
                {lista.length}
                <small>{lista.length === 1 ? "brecha abierta" : "brechas abiertas"}</small>
              </p>
              {lista.length > 0 ? (
                <>
                  <div className="stack" aria-hidden="true">
                    {niveles.map((s) => (
                      <span key={s} className={`sev-${SEVERIDAD_TONO[s]}`} style={{ flex: conteo[s] }} />
                    ))}
                  </div>
                  <p className="stack-leyenda">
                    {niveles.map((s) => (
                      <span key={s} className={`sev-${SEVERIDAD_TONO[s]}`}>
                        <i aria-hidden="true" />
                        {conteo[s]} {pluralSeveridad(s, conteo[s])}
                      </span>
                    ))}
                  </p>
                  {top ? (
                    <div className="gap-item">
                      <div className="gap-top">
                        <span className="code" style={{ marginLeft: 0 }}>#{top.prioridad}</span>
                        <BadgeSeveridad severidad={top.severidad} />
                      </div>
                      <p>{top.descripcion}</p>
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="card-sub">Sin brechas abiertas con estos filtros. Buen trabajo.</p>
              )}
              <Link href={href("/panel/brechas", filtrosAParams(v.filtros))} className="btn btn-ghost btn-sm" style={{ justifySelf: "start" }}>
                Abrir listado
                <Icon name="flecha" />
              </Link>
            </li>
          );
        })}
        {vistas.length < MAX_VISTAS ? (
          <li className="pin-card pin-vacia">
            <Icon name="fijar" width={22} height={22} style={{ color: "var(--accent)" }} />
            <p>
              Fija hasta {MAX_VISTAS} listados filtrados desde Brechas, por ejemplo las críticas de un dominio, para seguirlos aquí.
            </p>
            <Link href={href("/panel/brechas")} className="btn btn-ghost btn-sm" style={{ justifySelf: "start" }}>
              Ir a Brechas
              <Icon name="flecha" />
            </Link>
          </li>
        ) : null}
      </ul>
    </section>
  );
}
