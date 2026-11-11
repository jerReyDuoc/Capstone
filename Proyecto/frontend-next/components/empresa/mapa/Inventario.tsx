"use client";

/** Vista de tabla del mapa: sistemas y bases de datos, terceros y flujos (alternativa accesible al diagrama). */
import { useMemo, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import {
  aplicarFiltros, ETIQUETA_TIPO, filtrosActivos, nombreDato, nombreOpcion, nombrePais, nombreSubtipo, nombreTitular, plural,
  type CatalogoMapa, type ElementoMapa, type FiltrosMapa, type FlujoMapa, type VistaMapa,
} from "@/lib/mapaDatos";
import { Etiquetas } from "./PanelDetalle";
import s from "./mapa.module.css";

export function Inventario({
  catalogo,
  vista,
  filtros,
  onVer,
  onEditarElemento,
  onEditarFlujo,
  onEliminarElemento,
  onEliminarFlujo,
  ocupado,
}: {
  catalogo: CatalogoMapa;
  vista: VistaMapa;
  filtros: FiltrosMapa;
  onVer: (tipo: "elemento" | "flujo", id: number) => void;
  onEditarElemento: (e: ElementoMapa) => void;
  onEditarFlujo: (f: FlujoMapa) => void;
  onEliminarElemento: (e: ElementoMapa) => void;
  onEliminarFlujo: (f: FlujoMapa) => void;
  ocupado: boolean;
}) {
  const [busqueda, setBusqueda] = useState("");
  const q = busqueda.trim().toLowerCase();
  const visibles = useMemo(() => aplicarFiltros(vista, filtros), [vista, filtros]);
  const porId = useMemo(() => new Map(vista.elementos.map((e) => [e.id, e])), [vista.elementos]);

  const coincideElemento = (e: ElementoMapa) =>
    !q ||
    [e.nombre, e.proveedor ?? "", e.responsable ?? "", e.descripcion ?? "", nombrePais(catalogo, e.derivados.pais_efectivo),
      ...e.categorias_datos.map((c) => nombreDato(catalogo, c)), ...e.categorias_titulares.map((c) => nombreTitular(catalogo, c))]
      .join(" ").toLowerCase().includes(q);
  const coincideFlujo = (f: FlujoMapa) =>
    !q ||
    [porId.get(f.origen_id)?.nombre ?? "", porId.get(f.destino_id)?.nombre ?? "", f.finalidad ?? "",
      ...f.categorias_datos.map((c) => nombreDato(catalogo, c))].join(" ").toLowerCase().includes(q);

  const internos = vista.elementos.filter((e) => e.tipo !== "tercero" && visibles.elementos.has(e.id) && coincideElemento(e));
  const terceros = vista.elementos.filter((e) => e.tipo === "tercero" && visibles.elementos.has(e.id) && coincideElemento(e));
  const flujos = vista.flujos.filter((f) => visibles.flujos.has(f.id) && coincideFlujo(f));
  const orden = (a: ElementoMapa, b: ElementoMapa) => a.tipo.localeCompare(b.tipo) || a.nombre.localeCompare(b.nombre, "es");

  const nombre = (e: ElementoMapa) => (
    <div className={s.celdaNombre}>
      <button type="button" onClick={() => onVer("elemento", e.id)} title="Ver en el mapa">{e.nombre}</button>
      <small>
        {ETIQUETA_TIPO[e.tipo]}
        {e.subtipo ? ` · ${nombreSubtipo(catalogo, e.tipo, e.subtipo)}` : ""}
        {e.pendiente_revision ? " · por confirmar" : ""}
      </small>
    </div>
  );
  const accionesElemento = (e: ElementoMapa) => (
    <div className={s.accionesFila}>
      <button type="button" className="icon-btn" onClick={() => onEditarElemento(e)} disabled={ocupado} aria-label={`Editar ${e.nombre}`} title="Editar">
        <Icon name="editar" />
      </button>
      <button type="button" className="icon-btn" onClick={() => onEliminarElemento(e)} disabled={ocupado} aria-label={`Eliminar ${e.nombre}`} title="Eliminar">
        <Icon name="basura" />
      </button>
    </div>
  );

  return (
    <div style={{ display: "grid", gap: 24 }}>
      <div className="toolbar">
        <div className="field field-grow">
          <label className="field-label" htmlFor="buscar-inventario">Buscar en el inventario</label>
          <div className="input-wrap">
            <Icon name="buscar" />
            <input
              id="buscar-inventario"
              type="search"
              className="input"
              placeholder="Nombre, proveedor, responsable, categoría…"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
            />
          </div>
        </div>
        {filtrosActivos(filtros) ? <p className={s.filtroResumen}>Se aplican los filtros del mapa.</p> : null}
      </div>

      <section className={s.seccion} aria-labelledby="inv-internos">
        <div className={s.seccionCabeza}>
          <h2 id="inv-internos">Sistemas y bases de datos</h2>
          <span className="card-sub">{plural(internos.length, "elemento", "elementos")}</span>
        </div>
        {internos.length ? (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Sistemas y bases de datos de la empresa</caption>
              <thead>
                <tr>
                  <th scope="col">Nombre</th>
                  <th scope="col">País</th>
                  <th scope="col">Proveedor</th>
                  <th scope="col">Responsable</th>
                  <th scope="col">Datos personales</th>
                  <th scope="col">Titulares</th>
                  <th scope="col"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {[...internos].sort(orden).map((e) => (
                  <tr key={e.id}>
                    <td>{nombre(e)}</td>
                    <td>{nombrePais(catalogo, e.derivados.pais_efectivo)}</td>
                    <td>{e.proveedor ?? "—"}</td>
                    <td>{e.responsable ?? <span className={s.sinDato}>Sin asignar</span>}</td>
                    <td><Etiquetas catalogo={catalogo} codigos={e.categorias_datos} modo="datos" /></td>
                    <td>
                      <Etiquetas catalogo={catalogo} codigos={e.categorias_titulares} modo="titulares" />
                      {e.incluye_nna && !e.categorias_titulares.includes("nna") ? <span className={s.etiqueta} data-tono="nna" style={{ marginTop: 4 }}>Incluye NNA</span> : null}
                    </td>
                    <td>{accionesElemento(e)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="card-sub">No hay sistemas ni bases de datos que mostrar.</p>
        )}
      </section>

      <section className={s.seccion} aria-labelledby="inv-terceros">
        <div className={s.seccionCabeza}>
          <h2 id="inv-terceros">Terceros y destinatarios</h2>
          <span className="card-sub">{plural(terceros.length, "tercero", "terceros")}</span>
        </div>
        {terceros.length ? (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Terceros que reciben o tratan datos de la empresa</caption>
              <thead>
                <tr>
                  <th scope="col">Tercero</th>
                  <th scope="col">Rol</th>
                  <th scope="col">País</th>
                  <th scope="col">Contrato</th>
                  <th scope="col">Datos que recibe</th>
                  <th scope="col"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {[...terceros].sort(orden).map((e) => {
                  const requiere = !e.rol_tercero || catalogo.roles_tercero.find((r) => r.codigo === e.rol_tercero)?.requiere_contrato;
                  const recibe = [...new Set([...e.categorias_datos, ...vista.flujos.filter((f) => f.destino_id === e.id).flatMap((f) => f.categorias_datos)])];
                  return (
                    <tr key={e.id}>
                      <td>{nombre(e)}</td>
                      <td>{nombreOpcion(catalogo.roles_tercero, e.rol_tercero)}</td>
                      <td>{nombrePais(catalogo, e.pais)}</td>
                      <td>
                        {!requiere ? "No requiere" : (
                          <span className={s.etiqueta} data-tono={e.contrato_firmado ? "ok" : "sensible"}>
                            {e.contrato_firmado === true ? "Firmado" : e.contrato_firmado === false ? "Sin contrato" : "Por confirmar"}
                          </span>
                        )}
                      </td>
                      <td><Etiquetas catalogo={catalogo} codigos={recibe} modo="datos" /></td>
                      <td>{accionesElemento(e)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="card-sub">No hay terceros que mostrar.</p>
        )}
      </section>

      <section className={s.seccion} aria-labelledby="inv-flujos">
        <div className={s.seccionCabeza}>
          <h2 id="inv-flujos">Flujos de datos</h2>
          <span className="card-sub">{plural(flujos.length, "flujo", "flujos")}</span>
        </div>
        {flujos.length ? (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Flujos de datos personales entre elementos</caption>
              <thead>
                <tr>
                  <th scope="col">Origen → destino</th>
                  <th scope="col">Finalidad</th>
                  <th scope="col">Datos</th>
                  <th scope="col">Cifrado</th>
                  <th scope="col">Transferencia</th>
                  <th scope="col"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {flujos.map((f) => (
                  <tr key={f.id}>
                    <td>
                      <div className={s.celdaNombre}>
                        <button type="button" onClick={() => onVer("flujo", f.id)} title="Ver en el mapa">
                          {porId.get(f.origen_id)?.nombre} → {porId.get(f.destino_id)?.nombre}
                        </button>
                        {f.pendiente_revision ? <small>por confirmar</small> : null}
                      </div>
                    </td>
                    <td>{f.finalidad ?? <span className={s.sinDato}>Sin informar</span>}</td>
                    <td><Etiquetas catalogo={catalogo} codigos={f.categorias_datos} modo="datos" /></td>
                    <td>{f.cifrado === true ? "Sí" : f.cifrado === false ? "No" : "No se sabe"}</td>
                    <td>
                      {f.derivados.internacional ? (
                        <span className={s.etiqueta} data-tono={f.derivados.garantia_valida ? "internacional" : "sensible"}>
                          {nombrePais(catalogo, f.derivados.pais_destino)} · {f.derivados.garantia_valida ? "con garantía" : "sin garantía"}
                        </span>
                      ) : (
                        "No"
                      )}
                    </td>
                    <td>
                      <div className={s.accionesFila}>
                        <button type="button" className="icon-btn" onClick={() => onEditarFlujo(f)} disabled={ocupado} aria-label="Editar flujo" title="Editar">
                          <Icon name="editar" />
                        </button>
                        <button type="button" className="icon-btn" onClick={() => onEliminarFlujo(f)} disabled={ocupado} aria-label="Eliminar flujo" title="Eliminar">
                          <Icon name="basura" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="card-sub">No hay flujos que mostrar.</p>
        )}
      </section>
    </div>
  );
}
