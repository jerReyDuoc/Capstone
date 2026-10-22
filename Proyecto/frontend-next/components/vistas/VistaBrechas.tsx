"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { InformeBrechas } from "@/components/brechas/InformeBrechas";
import { MatrizPriorizacion } from "@/components/brechas/MatrizPriorizacion";
import { TarjetasSeveridad } from "@/components/brechas/TarjetasSeveridad";
import { PageHeader } from "@/components/shell/PageHeader";
import { BadgeEstado, BadgeSeveridad, EstadoPanel } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { useVistasFijadas } from "@/hooks/useVistasFijadas";
import { ordenarBrechas } from "@/lib/adaptadores";
import { brechasACsv, descargarTexto, imprimirComoPdf, nombreArchivo } from "@/lib/exportar";
import {
  describirFiltros,
  filtrarBrechas,
  filtrosAParams,
  filtrosDesdeParams,
  hayFiltros,
  type FiltrosBrechas,
} from "@/lib/filtrosBrechas";
import { IMPACTO_TEXTO, SEVERIDAD_TONO, SEVERIDADES, pluralSeveridad } from "@/lib/severidad";
import type { BrechaVista, PanelVista, Severidad } from "@/lib/types";

type Orden = "prioridad" | "dominio";

export function VistaBrechas() {
  return (
    <>
      <PageHeader
        eyebrow="Brechas normativas priorizadas"
        titulo="Brechas"
        subtitulo="Controles no cumplidos o parcialmente cumplidos tras el autodiagnóstico, ordenados por severidad para enfocar primero los recursos donde el riesgo es mayor."
      />
      <EstadoPanel>{(p) => <ListadoPriorizado panel={p} />}</EstadoPanel>
    </>
  );
}

function ListadoPriorizado({ panel }: { panel: PanelVista }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { href } = usePanel();
  const { estaFijada, fijar, quitar } = useVistasFijadas(panel.evaluacionId);
  const idBuscar = useId();
  const idDominio = useId();
  const idEstado = useId();

  // Los filtros viven en la URL: se pueden compartir, sobreviven al "atrás" y son los que se fijan/exportan.
  const filtrosUrl = useMemo(() => filtrosDesdeParams(params), [params]);
  const [texto, setTexto] = useState(filtrosUrl.texto);
  const filtros: FiltrosBrechas = { ...filtrosUrl, texto };
  const [orden, setOrden] = useState<Orden>("prioridad");
  const [aviso, setAviso] = useState("");
  const [emitido, setEmitido] = useState(() => new Date());

  // Referencias a la URL vigente: el retardo de la búsqueda no debe usar filtros viejos.
  const ultimaUrl = useRef({ params, filtrosUrl });
  ultimaUrl.current = { params, filtrosUrl };

  const navegar = (f: FiltrosBrechas) => {
    const q = new URLSearchParams();
    const ev = ultimaUrl.current.params.get("evaluacion");
    if (ev) q.set("evaluacion", ev);
    for (const [k, v] of Object.entries(filtrosAParams(f))) q.set(k, v);
    const s = q.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };

  // Búsqueda: estado local inmediato y URL con retardo para no navegar en cada tecla.
  const saltarRetardo = useRef(true); // la primera vez (montaje) y al limpiar no se navega
  useEffect(() => {
    if (saltarRetardo.current) {
      saltarRetardo.current = false;
      return;
    }
    const t = setTimeout(() => {
      const vigente = ultimaUrl.current.filtrosUrl;
      if (vigente.texto.trim() !== texto.trim()) navegar({ ...vigente, texto });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [texto]);

  const setFiltro = (cambio: Partial<FiltrosBrechas>) => navegar({ ...filtros, ...cambio });
  const alternarSeveridad = (s: Severidad) =>
    setFiltro({
      severidades: filtros.severidades.includes(s)
        ? filtros.severidades.filter((x) => x !== s)
        : SEVERIDADES.filter((x) => x === s || filtros.severidades.includes(x)),
    });
  const limpiar = () => {
    if (texto !== "") saltarRetardo.current = true;
    setTexto("");
    navegar({ severidades: [], dominio: null, estado: null, texto: "" });
  };

  const dominios = useMemo(
    () => [...new Set(panel.brechas.map((b) => b.dominio))].sort((a, b) => a.localeCompare(b, "es")),
    [panel.brechas],
  );

  const filtradas = useMemo(() => {
    const lista = filtrarBrechas(panel.brechas, filtros);
    const cmp: Record<Orden, (a: BrechaVista, b: BrechaVista) => number> = {
      prioridad: (a, b) => a.prioridad - b.prioridad,
      dominio: (a, b) => a.dominio.localeCompare(b.dominio, "es") || ordenarBrechas(a, b),
    };
    return [...lista].sort(cmp[orden]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panel.brechas, filtrosUrl, texto, orden]);

  const porDominio = useMemo(
    () =>
      dominios.map((d) => {
        const de = panel.brechas.filter((b) => b.dominio === d);
        return [d, de.length, de.filter((b) => b.severidad === "Crítica").length] as const;
      }),
    [dominios, panel.brechas],
  );
  const maxDominio = Math.max(1, ...porDominio.map((x) => x[1]));

  const conFiltros = hayFiltros(filtros);
  const vistaFijada = estaFijada(filtros);
  const ariaSort = (o: Orden) => (orden === o ? "ascending" : "none");
  const sinClasificar = panel.brechasPorSeveridad["Sin clasificar"];

  const exportarPdf = () => {
    const ahora = new Date();
    flushSync(() => setEmitido(ahora)); // la fecha del informe es la del momento de exportar
    setAviso(`Abrimos la impresión: elige “Guardar como PDF” para descargar ${filtradas.length} brechas.`);
    imprimirComoPdf(nombreArchivo(panel.evaluacionId, ahora));
  };
  const exportarCsv = () => {
    descargarTexto(brechasACsv(filtradas), `${nombreArchivo(panel.evaluacionId)}.csv`);
    setAviso(`Descargamos ${filtradas.length} brechas en CSV, listo para Excel, Power BI o Looker Studio.`);
  };
  const alternarFijada = () => {
    if (vistaFijada) {
      quitar(vistaFijada.id);
      setAviso(`Quitamos la vista ${describirFiltros(filtros)} del Diagnóstico.`);
    } else if (fijar(filtros)) {
      setAviso(`Listo: la vista ${describirFiltros(filtros)} quedó fijada en el Diagnóstico.`);
    } else {
      setAviso("Este navegador no permite guardar la vista. Revisa si está en modo privado.");
    }
  };

  // Función (no componente) para que el botón no se remonte y conserve el foco al ordenar.
  const botonOrden = (o: Orden, textoBoton: string) => (
    <button type="button" className="sort-btn" onClick={() => setOrden(o)}>
      {textoBoton}
      <Icon name="ordenar" width={14} height={14} style={{ opacity: orden === o ? 1 : 0.5 }} />
    </button>
  );

  if (panel.brechas.length === 0) {
    return (
      <div className="state" role="status">
        <Icon name="escudo" width={32} height={32} style={{ color: "var(--accent)" }} />
        <h2>Sin brechas abiertas</h2>
        <p>
          Ninguno de los {panel.controlesEvaluados} controles evaluados quedó como no cumplido o parcialmente cumplido.
          {panel.enRevision > 0 ? ` Aún hay ${panel.enRevision} en revisión por la IA: si alguno resulta incumplido, aparecerá aquí.` : ""}
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="no-print" style={{ display: "grid", gap: "var(--sp-6)" }}>
        {/* Criterio 1: análisis automático, explicado en una línea */}
        <p className="analisis">
          <Icon name="chispa" />
          <span className="analisis-flujo">
            <span>
              <strong>{panel.controlesEvaluados}</strong> controles evaluados
            </span>
            <span className="sep" aria-hidden="true">→</span>
            <span>
              <strong>{panel.noCumplidos}</strong> no cumplidos y <strong>{panel.parciales}</strong> parciales
            </span>
            <span className="sep" aria-hidden="true">→</span>
            <span>
              <strong>{panel.brechas.length}</strong> brechas priorizadas
            </span>
          </span>
          {panel.enRevision > 0 ? (
            <span>
              · {panel.enRevision === 1
                ? "1 respuesta sigue en revisión por la IA y se sumará si resulta incumplida."
                : `${panel.enRevision} respuestas siguen en revisión por la IA y se sumarán si resultan incumplidas.`}
            </span>
          ) : null}
        </p>

        {/* Criterio 2: severidades (también filtran) */}
        <TarjetasSeveridad conteo={panel.brechasPorSeveridad} seleccion={filtros.severidades} onAlternar={alternarSeveridad} />

        <div className="grid">
          <div className="col-5 md-col-12" style={{ display: "grid" }}>
            <MatrizPriorizacion brechas={panel.brechas} />
          </div>
          <section className="card col-7 md-col-12" aria-labelledby="brechas-dominio-titulo" style={{ display: "grid", gap: 16, alignContent: "start" }}>
            <div>
              <h2 className="card-title" id="brechas-dominio-titulo">Brechas por dominio</h2>
              <p className="card-sub">Elige un dominio para filtrar el listado</p>
            </div>
            <ul className="gap-list">
              {porDominio.map(([d, total, criticas]) => (
                <li key={d}>
                  <button
                    type="button"
                    className="domain-filter"
                    aria-pressed={filtros.dominio === d}
                    onClick={() => setFiltro({ dominio: filtros.dominio === d ? null : d })}
                  >
                    <span className="domain-filter-name">{d}</span>
                    <span className="domain-bar" aria-hidden="true">
                      <span className="fill" style={{ width: `${(total / maxDominio) * 100}%` }} />
                    </span>
                    <span className="domain-filter-count">
                      {total}
                      {criticas ? (
                        <span style={{ color: "var(--critico)" }}>
                          {" "}
                          · {criticas} {pluralSeveridad("Crítica", criticas)}
                        </span>
                      ) : null}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>

        {/* Criterio 2 + 3: listado priorizado, filtros y exportación */}
        <section className="card" aria-labelledby="tabla-brechas-titulo" style={{ display: "grid", gap: 20, alignContent: "start" }}>
          <div className="card-head" style={{ marginBottom: 0, alignItems: "flex-end" }}>
            <div>
              <h2 className="card-title" id="tabla-brechas-titulo">Listado priorizado</h2>
              <p className="card-sub" role="status" aria-live="polite">
                {conFiltros
                  ? `Mostrando ${filtradas.length} de ${panel.brechas.length} brechas · ${describirFiltros(filtros)}`
                  : `${panel.brechas.length} brechas, de la más a la menos urgente`}
              </p>
            </div>
            <div className="export-group" role="group" aria-label="Exportar el listado filtrado">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-pressed={Boolean(vistaFijada)}
                onClick={alternarFijada}
              >
                <Icon name="fijar" />
                {vistaFijada ? "Fijada en Diagnóstico" : "Fijar en Diagnóstico"}
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={exportarCsv} disabled={filtradas.length === 0}>
                <Icon name="tabla" />
                Exportar CSV
              </button>
              <button type="button" className="btn btn-primary btn-sm" onClick={exportarPdf} disabled={filtradas.length === 0}>
                <Icon name="pdf" />
                Exportar PDF
              </button>
            </div>
          </div>

          <p className="aviso-accion" role="status" aria-live="polite" hidden={!aviso}>
            {aviso}
            {aviso && vistaFijada ? (
              <>
                {" "}
                <Link href={href("/panel")}>Ver en Diagnóstico</Link>
              </>
            ) : null}
          </p>

          <div className="toolbar">
            <div className="field field-grow">
              <label className="field-label" htmlFor={idBuscar}>Buscar</label>
              <div className="input-wrap">
                <Icon name="buscar" />
                <input
                  id={idBuscar}
                  type="search"
                  className="input"
                  placeholder="Código, brecha o acción"
                  aria-describedby={`${idBuscar}-ayuda`}
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <span id={`${idBuscar}-ayuda`} className="sr-only">Busca en código, descripción, acción sugerida y ruta formativa.</span>
            </div>
            <div className="field">
              <label className="field-label" htmlFor={idDominio}>Dominio</label>
              <select id={idDominio} className="select" value={filtros.dominio ?? ""} onChange={(e) => setFiltro({ dominio: e.target.value || null })}>
                <option value="">Todos los dominios</option>
                {dominios.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field-label" htmlFor={idEstado}>Estado</label>
              <select
                id={idEstado}
                className="select"
                style={{ minWidth: 200 }}
                value={filtros.estado ?? ""}
                onChange={(e) => setFiltro({ estado: (e.target.value || null) as FiltrosBrechas["estado"] })}
              >
                <option value="">Todos</option>
                <option value="no_cumplido">No cumplido</option>
                <option value="parcialmente_cumplido">Parcialmente cumplido</option>
              </select>
            </div>
            {conFiltros ? (
              <button type="button" className="btn btn-ghost" onClick={limpiar}>
                Limpiar filtros
              </button>
            ) : null}
          </div>

          {sinClasificar > 0 && (filtros.severidades.length === 0 || filtros.severidades.includes("Sin clasificar")) ? (
            <p className="card-sub">
              Incluye {sinClasificar} {sinClasificar === 1 ? "brecha" : "brechas"} sin impacto en el catálogo, al final de la lista.{" "}
              <button
                type="button"
                className="link-btn"
                aria-pressed={filtros.severidades.includes("Sin clasificar")}
                onClick={() => alternarSeveridad("Sin clasificar")}
              >
                {filtros.severidades.includes("Sin clasificar") ? "Ver todas" : "Ver solo esas"}
              </button>
            </p>
          ) : null}

          {filtradas.length === 0 ? (
            <div className="state">
              <h2>Sin resultados</h2>
              <p>Ninguna brecha coincide con los filtros elegidos. Prueba quitando alguno.</p>
              <button type="button" className="btn btn-ghost" onClick={limpiar}>
                Limpiar filtros
              </button>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <caption className="sr-only">
                  Brechas abiertas ordenadas por {orden === "prioridad" ? "prioridad" : "dominio"}. La columna Prioridad indica el
                  orden de atención recomendado.
                </caption>
                <thead>
                  <tr>
                    <th scope="col" aria-sort={ariaSort("prioridad")}>{botonOrden("prioridad", "Prioridad")}</th>
                    <th scope="col">Severidad</th>
                    <th scope="col">Brecha detectada</th>
                    <th scope="col" aria-sort={ariaSort("dominio")}>{botonOrden("dominio", "Dominio")}</th>
                    <th scope="col">Acción y ruta formativa</th>
                  </tr>
                </thead>
                <tbody>
                  {filtradas.map((b) => (
                    <tr key={b.respuestaId} data-sev={b.severidad} className={`sev-${SEVERIDAD_TONO[b.severidad]}`}>
                      <td className="rank">
                        <span className="sr-only">Prioridad </span>
                        {b.prioridad}
                      </td>
                      <td>
                        <span style={{ display: "grid", gap: 6, justifyItems: "start" }}>
                          <BadgeSeveridad severidad={b.severidad} />
                          <BadgeEstado estado={b.estado} />
                        </span>
                      </td>
                      <td style={{ minWidth: 260 }}>
                        <span className="brecha-desc">{b.descripcion}</span>
                        <span className="brecha-codigos">
                          <span>{b.codigo}</span>
                          {b.controlCodigo && b.controlCodigo !== b.codigo ? <span>· Control {b.controlCodigo}</span> : null}
                          {b.criticidad !== "Sin clasificar" ? <span>· Impacto {IMPACTO_TEXTO[b.criticidad]}</span> : null}
                        </span>
                      </td>
                      <td>{b.dominio}</td>
                      <td style={{ minWidth: 200 }}>
                        {b.accion ?? "—"}
                        {b.rutaFormativa ? (
                          <span className="ruta">
                            <Icon name="libro" />
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

      <InformeBrechas panel={panel} brechas={filtradas} filtros={filtros} emitido={emitido} />
    </>
  );
}
