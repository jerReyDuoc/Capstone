"use client";

/**
 * Inventario del mapa: sistemas y bases de datos, terceros y flujos en tablas (alternativa accesible al
 * diagrama). Búsqueda, vista por tipo, "solo con información pendiente", el estado de cada registro (qué
 * le falta, si está por confirmar) y acciones claras. Al hacer clic en un nombre se abre su ficha; en el
 * teléfono cada fila se muestra como una tarjeta.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";
import {
  aplicarFiltros, ETIQUETA_TIPO, filtrosActivos, nombreDato, nombreOpcion, nombrePais, nombreSubtipo, nombreTitular, plural,
  type CatalogoMapa, type ElementoMapa, type FiltrosMapa, type FlujoMapa, type PendienteMapa, type TipoElemento, type VistaMapa,
} from "@/lib/mapaDatos";
import { Etiquetas, ICONO_TIPO } from "./PanelDetalle";
import s from "./mapa.module.css";

type Vista = "todo" | "internos" | "terceros" | "flujos";

export function Inventario({
  catalogo,
  vista,
  filtros,
  onVer,
  onAbrir,
  onAgregar,
  onAgregarFlujo,
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
  onAbrir: (tipo: "elemento" | "flujo", id: number) => void;
  onAgregar: (tipo: TipoElemento) => void;
  onAgregarFlujo: () => void;
  onEditarElemento: (e: ElementoMapa) => void;
  onEditarFlujo: (f: FlujoMapa) => void;
  onEliminarElemento: (e: ElementoMapa) => void;
  onEliminarFlujo: (f: FlujoMapa) => void;
  ocupado: boolean;
}) {
  const [busqueda, setBusqueda] = useState("");
  const [ver, setVer] = useState<Vista>("todo");
  const [soloPendientes, setSoloPendientes] = useState(false);
  const q = busqueda.trim().toLowerCase();
  const visibles = useMemo(() => aplicarFiltros(vista, filtros), [vista, filtros]);
  const porId = useMemo(() => new Map(vista.elementos.map((e) => [e.id, e])), [vista.elementos]);
  const pendiente = useMemo(() => {
    const m = new Map<string, PendienteMapa>();
    for (const p of vista.completitud.pendientes) m.set(`${p.tipo}-${p.id}`, p);
    return m;
  }, [vista.completitud.pendientes]);

  const tienePendiente = (tipo: "elemento" | "flujo", id: number) => {
    const p = pendiente.get(`${tipo}-${id}`);
    return Boolean(p && (p.faltan.length || p.por_confirmar));
  };
  const coincideElemento = (e: ElementoMapa) =>
    (!soloPendientes || tienePendiente("elemento", e.id)) && (!q ||
    [e.nombre, e.proveedor ?? "", e.responsable ?? "", e.descripcion ?? "", nombrePais(catalogo, e.derivados.pais_efectivo),
      ...e.categorias_datos.map((c) => nombreDato(catalogo, c)), ...e.categorias_titulares.map((c) => nombreTitular(catalogo, c))]
      .join(" ").toLowerCase().includes(q));
  const coincideFlujo = (f: FlujoMapa) =>
    (!soloPendientes || tienePendiente("flujo", f.id)) && (!q ||
    [porId.get(f.origen_id)?.nombre ?? "", porId.get(f.destino_id)?.nombre ?? "", f.finalidad ?? "",
      ...f.categorias_datos.map((c) => nombreDato(catalogo, c))].join(" ").toLowerCase().includes(q));

  const orden = (a: ElementoMapa, b: ElementoMapa) => a.tipo.localeCompare(b.tipo) || a.nombre.localeCompare(b.nombre, "es");
  const internos = vista.elementos.filter((e) => e.tipo !== "tercero" && visibles.elementos.has(e.id) && coincideElemento(e)).sort(orden);
  const terceros = vista.elementos.filter((e) => e.tipo === "tercero" && visibles.elementos.has(e.id) && coincideElemento(e)).sort(orden);
  const flujos = vista.flujos.filter((f) => visibles.flujos.has(f.id) && coincideFlujo(f));
  const totalPendientes = vista.completitud.pendientes.filter((p) => p.faltan.length || p.por_confirmar).length;

  const estado = (tipo: "elemento" | "flujo", id: number) => {
    const p = pendiente.get(`${tipo}-${id}`);
    if (!p || (!p.faltan.length && !p.por_confirmar)) {
      return <span className={s.estadoRegistro} data-tono="ok"><Icon name="check" />Completo</span>;
    }
    return (
      <span className={s.estadoRegistroLista}>
        {p.por_confirmar ? <span className={s.estadoRegistro} data-tono="pendiente">Por confirmar</span> : null}
        {p.faltan.length ? (
          <span className={s.estadoRegistro} data-tono="falta" title={`Falta: ${p.faltan.join(", ")}`}>
            <Icon name="alerta" />Falta: {p.faltan.slice(0, 2).join(", ")}{p.faltan.length > 2 ? ` y ${p.faltan.length - 2} más` : ""}
          </span>
        ) : null}
      </span>
    );
  };

  const nombre = (e: ElementoMapa) => (
    <div className={s.celdaNombre}>
      <span className={s.celdaIcono} data-tipo={e.tipo} aria-hidden="true"><Icon name={ICONO_TIPO[e.tipo]} /></span>
      <span>
        <button type="button" onClick={() => onAbrir("elemento", e.id)} title="Ver la ficha">{e.nombre}</button>
        <small>
          {ETIQUETA_TIPO[e.tipo]}
          {e.subtipo ? ` · ${nombreSubtipo(catalogo, e.tipo, e.subtipo)}` : ""}
        </small>
      </span>
    </div>
  );
  const acciones = (editar: () => void, eliminar: () => void, verMapa: () => void, etiqueta: string) => (
    <div className={s.accionesFila}>
      <button type="button" className="icon-btn" onClick={verMapa} aria-label={`Ver ${etiqueta} en el mapa`} title="Ver en el mapa">
        <Icon name="mapa" />
      </button>
      <button type="button" className="btn btn-ghost btn-sm" onClick={editar} disabled={ocupado} aria-label={`Editar ${etiqueta}`}>
        <Icon name="editar" />
        <span className={s.textoAccion}>Editar</span>
      </button>
      <button type="button" className={`icon-btn ${s.iconoEliminar}`} onClick={eliminar} disabled={ocupado} aria-label={`Eliminar ${etiqueta}`} title="Eliminar">
        <Icon name="basura" />
      </button>
    </div>
  );

  const vistas: { id: Vista; titulo: string; n: number }[] = [
    { id: "todo", titulo: "Todo", n: internos.length + terceros.length + flujos.length },
    { id: "internos", titulo: "Sistemas y bases", n: internos.length },
    { id: "terceros", titulo: "Terceros", n: terceros.length },
    { id: "flujos", titulo: "Flujos", n: flujos.length },
  ];

  return (
    <div className={s.inventario}>
      <div className={s.inventarioBarra}>
        <div className={`input-wrap ${s.inventarioBuscar}`}>
          <Icon name="buscar" />
          <input
            id="buscar-inventario"
            type="search"
            className="input"
            placeholder="Buscar por nombre, proveedor, responsable o categoría"
            aria-label="Buscar en el inventario"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
          />
        </div>
        <div className="chip-group" role="group" aria-label="Qué mostrar">
          {vistas.map((v) => (
            <button key={v.id} type="button" className="chip" aria-pressed={ver === v.id} onClick={() => setVer(v.id)}>
              {v.titulo} <span aria-hidden="true">· {v.n}</span>
            </button>
          ))}
          <button type="button" className="chip" aria-pressed={soloPendientes} onClick={() => setSoloPendientes((x) => !x)} disabled={!totalPendientes && !soloPendientes}>
            <Icon name="alerta" width={14} height={14} />
            Con pendientes <span aria-hidden="true">· {totalPendientes}</span>
          </button>
        </div>
      </div>
      {filtrosActivos(filtros) ? <p className={s.filtroResumen}>Se aplican los filtros del mapa.</p> : null}

      {ver === "todo" || ver === "internos" ? (
        <Seccion
          id="inv-internos"
          titulo="Sistemas y bases de datos"
          conteo={plural(internos.length, "elemento", "elementos")}
          accion={<button type="button" className="btn btn-ghost btn-sm" onClick={() => onAgregar("sistema")} disabled={ocupado}><Icon name="mas" />Agregar</button>}
          vacio="No hay sistemas ni bases de datos que mostrar."
          hay={internos.length > 0}
        >
          <table className={`table ${s.tablaInventario}`}>
            <caption className="sr-only">Sistemas y bases de datos de la empresa</caption>
            <thead>
              <tr>
                <th scope="col">Nombre</th>
                <th scope="col">País</th>
                <th scope="col">Responsable</th>
                <th scope="col">Datos personales</th>
                <th scope="col">Estado</th>
                <th scope="col"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {internos.map((e) => (
                <tr key={e.id}>
                  <td data-label="Nombre">{nombre(e)}</td>
                  <td data-label="País">{e.derivados.pais_efectivo ? nombrePais(catalogo, e.derivados.pais_efectivo) : <span className={s.sinDato}>Sin informar</span>}</td>
                  <td data-label="Responsable">{e.responsable ?? <span className={s.sinDato}>Sin asignar</span>}</td>
                  <td data-label="Datos personales">
                    <Etiquetas catalogo={catalogo} codigos={e.categorias_datos} modo="datos" />
                    {e.categorias_titulares.length ? (
                      <small className={s.celdaNota}>De: {e.categorias_titulares.map((c) => nombreTitular(catalogo, c)).join(", ")}</small>
                    ) : null}
                  </td>
                  <td data-label="Estado">{estado("elemento", e.id)}</td>
                  <td data-label="Acciones">{acciones(() => onEditarElemento(e), () => onEliminarElemento(e), () => onVer("elemento", e.id), e.nombre)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Seccion>
      ) : null}

      {ver === "todo" || ver === "terceros" ? (
        <Seccion
          id="inv-terceros"
          titulo="Terceros y destinatarios"
          conteo={plural(terceros.length, "tercero", "terceros")}
          accion={<button type="button" className="btn btn-ghost btn-sm" onClick={() => onAgregar("tercero")} disabled={ocupado}><Icon name="mas" />Agregar</button>}
          vacio="No hay terceros que mostrar."
          hay={terceros.length > 0}
        >
          <table className={`table ${s.tablaInventario}`}>
            <caption className="sr-only">Terceros que reciben o tratan datos de la empresa</caption>
            <thead>
              <tr>
                <th scope="col">Tercero</th>
                <th scope="col">Rol</th>
                <th scope="col">País</th>
                <th scope="col">Contrato</th>
                <th scope="col">Datos que recibe</th>
                <th scope="col">Estado</th>
                <th scope="col"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {terceros.map((e) => {
                const requiere = !e.rol_tercero || catalogo.roles_tercero.find((r) => r.codigo === e.rol_tercero)?.requiere_contrato;
                const recibe = [...new Set([...e.categorias_datos, ...vista.flujos.filter((f) => f.destino_id === e.id).flatMap((f) => f.categorias_datos)])];
                return (
                  <tr key={e.id}>
                    <td data-label="Tercero">{nombre(e)}</td>
                    <td data-label="Rol">{e.rol_tercero ? nombreOpcion(catalogo.roles_tercero, e.rol_tercero) : <span className={s.sinDato}>Sin indicar</span>}</td>
                    <td data-label="País">{e.pais ? nombrePais(catalogo, e.pais) : <span className={s.sinDato}>Sin informar</span>}</td>
                    <td data-label="Contrato">
                      {!requiere ? "No requiere" : (
                        <span className={s.etiqueta} data-tono={e.contrato_firmado ? "ok" : "sensible"}>
                          {e.contrato_firmado === true ? "Firmado" : e.contrato_firmado === false ? "Sin contrato" : "Por confirmar"}
                        </span>
                      )}
                    </td>
                    <td data-label="Datos que recibe"><Etiquetas catalogo={catalogo} codigos={recibe} modo="datos" /></td>
                    <td data-label="Estado">{estado("elemento", e.id)}</td>
                    <td data-label="Acciones">{acciones(() => onEditarElemento(e), () => onEliminarElemento(e), () => onVer("elemento", e.id), e.nombre)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Seccion>
      ) : null}

      {ver === "todo" || ver === "flujos" ? (
        <Seccion
          id="inv-flujos"
          titulo="Flujos de datos"
          conteo={plural(flujos.length, "flujo", "flujos")}
          accion={<button type="button" className="btn btn-ghost btn-sm" onClick={onAgregarFlujo} disabled={ocupado || vista.elementos.length < 2}><Icon name="mas" />Agregar</button>}
          vacio="No hay flujos que mostrar."
          hay={flujos.length > 0}
        >
          <table className={`table ${s.tablaInventario}`}>
            <caption className="sr-only">Flujos de datos personales entre elementos</caption>
            <thead>
              <tr>
                <th scope="col">Origen → destino</th>
                <th scope="col">Finalidad</th>
                <th scope="col">Datos</th>
                <th scope="col">Cifrado</th>
                <th scope="col">Transferencia</th>
                <th scope="col">Estado</th>
                <th scope="col"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {flujos.map((f) => {
                const o = porId.get(f.origen_id);
                const d = porId.get(f.destino_id);
                const etiqueta = `el flujo de ${o?.nombre ?? "?"} a ${d?.nombre ?? "?"}`;
                return (
                  <tr key={f.id}>
                    <td data-label="Origen → destino">
                      <div className={s.celdaNombre}>
                        <span className={s.celdaIcono} aria-hidden="true"><Icon name={f.derivados.internacional ? "globo" : "flujo"} /></span>
                        <span>
                          <button type="button" onClick={() => onAbrir("flujo", f.id)} title="Ver la ficha">
                            {o?.nombre} → {d?.nombre}
                          </button>
                          {f.derivados.hacia_tercero ? <small>Hacia un tercero</small> : null}
                        </span>
                      </div>
                    </td>
                    <td data-label="Finalidad">{f.finalidad ?? <span className={s.sinDato}>Sin informar</span>}</td>
                    <td data-label="Datos"><Etiquetas catalogo={catalogo} codigos={f.categorias_datos} modo="datos" /></td>
                    <td data-label="Cifrado">
                      {f.cifrado === true ? <span className={s.etiqueta} data-tono="ok">Sí</span>
                        : f.cifrado === false ? <span className={s.etiqueta} data-tono="sensible">No</span>
                          : <span className={s.sinDato}>No se sabe</span>}
                    </td>
                    <td data-label="Transferencia">
                      {f.derivados.internacional ? (
                        <span className={s.etiqueta} data-tono={f.derivados.garantia_valida ? "internacional" : "sensible"}>
                          {nombrePais(catalogo, f.derivados.pais_destino)} · {f.derivados.garantia_valida ? "con garantía" : "sin garantía"}
                        </span>
                      ) : "No sale de Chile"}
                    </td>
                    <td data-label="Estado">{estado("flujo", f.id)}</td>
                    <td data-label="Acciones">{acciones(() => onEditarFlujo(f), () => onEliminarFlujo(f), () => onVer("flujo", f.id), etiqueta)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Seccion>
      ) : null}
    </div>
  );
}

function Seccion({ id, titulo, conteo, accion, vacio, hay, children }: {
  id: string;
  titulo: string;
  conteo: string;
  accion: ReactNode;
  vacio: string;
  hay: boolean;
  children: ReactNode;
}) {
  return (
    <section className={s.seccion} aria-labelledby={id}>
      <div className={s.seccionCabeza}>
        <div className={s.seccionTitulo}>
          <h2 id={id}>{titulo}</h2>
          <span className="card-sub">{conteo}</span>
        </div>
        {accion}
      </div>
      {hay ? <div className={`table-wrap ${s.envolturaTabla}`}>{children}</div> : <p className={s.vacioSeccion}>{vacio}</p>}
    </section>
  );
}
