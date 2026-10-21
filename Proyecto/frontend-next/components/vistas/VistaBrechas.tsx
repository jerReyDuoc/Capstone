"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, useMemo, useState } from "react";
import { BarrasCriticidad } from "@/components/charts/BarrasCriticidad";
import { PageHeader } from "@/components/shell/PageHeader";
import { BadgeCriticidad, BadgeEstado, EstadoPanel } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { ordenarBrechas } from "@/lib/adaptadores";
import { CRITICIDADES } from "@/lib/madurez";
import type { BrechaVista, Criticidad, PanelVista } from "@/lib/types";

type Orden = "prioridad" | "codigo" | "dominio";

export function VistaBrechas() {
  return (
    <>
      <PageHeader
        eyebrow="Brechas priorizadas"
        titulo="Brechas"
        subtitulo="Controles no cumplidos o parcialmente cumplidos, con la acción sugerida y la ruta formativa para cerrarlos."
      />
      <EstadoPanel>{(p) => <TablaBrechas panel={p} />}</EstadoPanel>
    </>
  );
}

function TablaBrechas({ panel }: { panel: PanelVista }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const idDominio = useId();
  const idEstado = useId();

  // Los filtros viven en la URL: se pueden compartir y sobreviven al "atrás".
  const criticidad = (params.get("criticidad") as Criticidad | null) ?? null;
  const dominio = params.get("dominio") ?? "";
  const estado = params.get("estado") ?? "";
  const [orden, setOrden] = useState<Orden>("prioridad");

  const setFiltro = (clave: string, valor: string | null) => {
    const q = new URLSearchParams(params.toString());
    if (valor) q.set(clave, valor);
    else q.delete(clave);
    router.replace(`${pathname}?${q.toString()}`, { scroll: false });
  };

  const dominios = useMemo(() => [...new Set(panel.brechas.map((b) => b.dominio))].sort(), [panel.brechas]);

  const filtradas = useMemo(() => {
    const lista = panel.brechas.filter(
      (b) =>
        (!criticidad || b.criticidad === criticidad) &&
        (!dominio || b.dominio === dominio) &&
        (!estado || b.estado === estado),
    );
    const cmp: Record<Orden, (a: BrechaVista, b: BrechaVista) => number> = {
      prioridad: ordenarBrechas,
      codigo: (a, b) => a.codigo.localeCompare(b.codigo, "es"),
      dominio: (a, b) => a.dominio.localeCompare(b.dominio, "es") || ordenarBrechas(a, b),
    };
    return [...lista].sort(cmp[orden]);
  }, [panel.brechas, criticidad, dominio, estado, orden]);

  const porDominio = useMemo(
    () =>
      dominios.map((d) => {
        const de = panel.brechas.filter((b) => b.dominio === d);
        return [d, de.length, de.filter((b) => b.criticidad === "Alta").length] as const;
      }),
    [dominios, panel.brechas],
  );
  const maxDominio = Math.max(1, ...porDominio.map((x) => x[1]));

  const hayFiltros = Boolean(criticidad || dominio || estado);
  const ariaSort = (o: Orden) => (orden === o ? "ascending" : "none");

  // Función (no componente) para que el botón no se remonte y conserve el foco al ordenar.
  const botonOrden = (o: Orden, texto: string) => (
    <button type="button" className="sort-btn" onClick={() => setOrden(o)}>
      {texto}
      <Icon name="ordenar" width={14} height={14} style={{ opacity: orden === o ? 1 : 0.5 }} />
    </button>
  );

  return (
    <div className="grid">
      <div className="card col-5 md-col-5">
        <BarrasCriticidad
          conteo={panel.brechasPorCriticidad}
          onSeleccionar={(c) => setFiltro("criticidad", criticidad === c ? null : c)}
        />
      </div>

      <section className="card col-7 md-col-7" aria-labelledby="brechas-dominio-titulo" style={{ display: "grid", gap: 16, alignContent: "start" }}>
        <div>
          <h2 className="card-title" id="brechas-dominio-titulo">Brechas por dominio</h2>
          <p className="card-sub">Elige un dominio para filtrar el listado</p>
        </div>
        <ul className="gap-list">
          {porDominio.map(([d, total, altas]) => (
            <li key={d}>
              <button
                type="button"
                className="domain-filter"
                aria-pressed={dominio === d}
                onClick={() => setFiltro("dominio", dominio === d ? null : d)}
              >
                <span className="domain-filter-name">{d}</span>
                <span className="domain-bar" aria-hidden="true">
                  <span className="fill" style={{ width: `${(total / maxDominio) * 100}%` }} />
                </span>
                <span className="domain-filter-count">
                  {total}
                  {altas ? <span style={{ color: "var(--alto)" }}> · {altas} alta{altas > 1 ? "s" : ""}</span> : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="card col-12" aria-labelledby="tabla-brechas-titulo" style={{ display: "grid", gap: 20, alignContent: "start" }}>
        <div className="card-head" style={{ marginBottom: 0 }}>
          <div>
            <h2 className="card-title" id="tabla-brechas-titulo">Listado de brechas</h2>
            <p className="card-sub" role="status" aria-live="polite">
              Mostrando {filtradas.length} de {panel.brechas.length} brechas
            </p>
          </div>
          {hayFiltros ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => router.replace(`${pathname}?${evaluacionSolo(params)}`, { scroll: false })}>
              Limpiar filtros
            </button>
          ) : null}
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-end" }}>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="field-label" style={{ marginBottom: 6 }}>Criticidad</legend>
            <div className="chip-group">
              {CRITICIDADES.filter((c) => panel.brechasPorCriticidad[c] > 0).map((c) => (
                <button
                  key={c}
                  type="button"
                  className="chip"
                  aria-pressed={criticidad === c}
                  onClick={() => setFiltro("criticidad", criticidad === c ? null : c)}
                >
                  {c} ({panel.brechasPorCriticidad[c]})
                </button>
              ))}
            </div>
          </fieldset>
          <div className="field">
            <label className="field-label" htmlFor={idDominio}>Dominio</label>
            <select id={idDominio} className="select" value={dominio} onChange={(e) => setFiltro("dominio", e.target.value)}>
              <option value="">Todos los dominios</option>
              {dominios.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label className="field-label" htmlFor={idEstado}>Estado</label>
            <select id={idEstado} className="select" style={{ minWidth: 180 }} value={estado} onChange={(e) => setFiltro("estado", e.target.value)}>
              <option value="">Todos</option>
              <option value="no_cumplido">No cumplido</option>
              <option value="parcialmente_cumplido">Parcialmente cumplido</option>
            </select>
          </div>
        </div>

        {filtradas.length === 0 ? (
          <div className="state">
            <h2>Sin resultados</h2>
            <p>Ninguna brecha coincide con los filtros elegidos.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Brechas abiertas, ordenadas por {orden}</caption>
              <thead>
                <tr>
                  <th scope="col" aria-sort={ariaSort("codigo")}>{botonOrden("codigo", "Código")}</th>
                  <th scope="col" aria-sort={ariaSort("prioridad")}>{botonOrden("prioridad", "Prioridad")}</th>
                  <th scope="col">Brecha detectada</th>
                  <th scope="col" aria-sort={ariaSort("dominio")}>{botonOrden("dominio", "Dominio")}</th>
                  <th scope="col">Acción y ruta formativa</th>
                </tr>
              </thead>
              <tbody>
                {filtradas.map((b) => (
                  <tr key={b.respuestaId}>
                    <td className="code">{b.codigo}</td>
                    <td>
                      <span style={{ display: "grid", gap: 6, justifyItems: "start" }}>
                        <BadgeCriticidad criticidad={b.criticidad} />
                        <BadgeEstado estado={b.estado} />
                      </span>
                    </td>
                    <td style={{ color: "var(--text)", minWidth: 220 }}>{b.descripcion}</td>
                    <td>{b.dominio}</td>
                    <td style={{ minWidth: 200 }}>
                      {b.accion ?? "—"}
                      {b.rutaFormativa ? (
                        <span style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4, color: "var(--accent)" }}>
                          <Icon name="libro" width={14} height={14} />
                          {b.rutaFormativa}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function evaluacionSolo(params: URLSearchParams | { get(k: string): string | null }) {
  const e = params.get("evaluacion");
  return e ? `evaluacion=${e}` : "";
}
