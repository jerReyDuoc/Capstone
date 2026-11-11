"use client";

/** Ficha del elemento o flujo elegido en el mapa, con sus flujos, riesgos y acciones. */
import { Icon, type IconName } from "@/components/ui/Icon";
import { fechaHoraChile } from "@/lib/fechas";
import {
  ETIQUETA_ORIGEN, ETIQUETA_TIPO, nombreDato, nombreOpcion, nombrePais, nombreSubtipo, nombreTitular,
  type CatalogoMapa, type ElementoMapa, type FlujoMapa, type HallazgoMapa, type TipoElemento, type VistaMapa,
} from "@/lib/mapaDatos";
import type { Seleccion } from "./GrafoMapa";
import s from "./mapa.module.css";

const ICONO: Record<TipoElemento, IconName> = { sistema: "sistemaApp", base_datos: "baseDatos", tercero: "empresa" };
const COLOR: Record<TipoElemento, string> = { sistema: "var(--accent)", base_datos: "var(--serie-industria)", tercero: "var(--naranja)" };

export function Etiquetas({ catalogo, codigos, modo, vacio = "Sin informar" }: {
  catalogo: CatalogoMapa | null;
  codigos: string[];
  modo: "datos" | "titulares";
  vacio?: string;
}) {
  if (!codigos.length) return <span className={s.sinDato}>{vacio}</span>;
  return (
    <ul className={s.etiquetas}>
      {codigos.map((c) => {
        const sensible = modo === "datos" && catalogo?.categorias_datos.find((x) => x.codigo === c)?.sensible;
        const nna = modo === "titulares" && catalogo?.categorias_titulares.find((x) => x.codigo === c)?.nna;
        return (
          <li key={c} className={s.etiqueta} data-tono={sensible ? "sensible" : nna ? "nna" : undefined}>
            {modo === "datos" ? nombreDato(catalogo, c) : nombreTitular(catalogo, c)}
            {sensible ? <span className="sr-only"> (dato sensible)</span> : null}
          </li>
        );
      })}
    </ul>
  );
}

export function PanelDetalle({
  catalogo,
  vista,
  seleccion,
  onSeleccionar,
  onEditarElemento,
  onEditarFlujo,
  onNuevoFlujo,
  onEliminarElemento,
  onEliminarFlujo,
  onConfirmar,
  ocupado,
}: {
  catalogo: CatalogoMapa;
  vista: VistaMapa;
  seleccion: Seleccion | null;
  onSeleccionar: (s: Seleccion | null) => void;
  onEditarElemento: (e: ElementoMapa) => void;
  onEditarFlujo: (f: FlujoMapa) => void;
  onNuevoFlujo: (origenId: number | null, destinoId?: number | null) => void;
  onEliminarElemento: (e: ElementoMapa) => void;
  onEliminarFlujo: (f: FlujoMapa) => void;
  onConfirmar: (sel: Seleccion) => void;
  ocupado: boolean;
}) {
  const porId = new Map(vista.elementos.map((e) => [e.id, e]));
  const riesgos = (sel: Seleccion): HallazgoMapa[] =>
    vista.hallazgos.filter((h) => (sel.tipo === "elemento" ? h.elementos.includes(sel.id) : h.flujos.includes(sel.id)));

  if (!seleccion) {
    return (
      <aside className={`card ${s.detalle}`} aria-label="Detalle del mapa">
        <div className={s.detalleVacio}>
          <h2 className="card-title">Explora tu mapa</h2>
          <p>Elige un elemento o un flujo para ver su ficha: qué datos trata, de quiénes, dónde están y con quién se comparten.</p>
          <ul>
            <li>Los bordes punteados marcan lo que está <strong>por confirmar</strong> (vino de una plantilla o de tu evaluación).</li>
            <li>Las líneas punteadas ámbar son <strong>transferencias internacionales</strong>.</li>
            <li>Las rosadas llevan <strong>datos sensibles</strong>.</li>
          </ul>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onNuevoFlujo(null)} disabled={vista.elementos.length < 2}>
            <Icon name="flujo" />
            Agregar un flujo
          </button>
        </div>
      </aside>
    );
  }

  if (seleccion.tipo === "elemento") {
    const e = porId.get(seleccion.id);
    if (!e) return null;
    const salientes = vista.flujos.filter((f) => f.origen_id === e.id);
    const entrantes = vista.flujos.filter((f) => f.destino_id === e.id);
    const lista = riesgos(seleccion);
    return (
      <aside className={`card ${s.detalle}`} aria-label={`Ficha de ${e.nombre}`}>
        <div className={s.detalleCabeza}>
          <span className={s.detalleTipo} style={{ color: COLOR[e.tipo] }}>
            <Icon name={ICONO[e.tipo]} />
            {ETIQUETA_TIPO[e.tipo]}
            {e.subtipo ? ` · ${nombreSubtipo(catalogo, e.tipo, e.subtipo)}` : ""}
          </span>
          <h2 className={s.detalleTitulo}>{e.nombre}</h2>
          <ul className={s.etiquetas}>
            {e.derivados.sensibles.length ? <li className={s.etiqueta} data-tono="sensible">Datos sensibles</li> : null}
            {e.incluye_nna ? <li className={s.etiqueta} data-tono="nna">Niños, niñas y adolescentes</li> : null}
            {e.derivados.fuera_de_chile ? <li className={s.etiqueta} data-tono="internacional">Fuera de Chile</li> : null}
            {e.pendiente_revision ? <li className={s.etiqueta} data-tono="pendiente">Por confirmar</li> : null}
          </ul>
        </div>
        <div className={s.acciones}>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onEditarElemento(e)} disabled={ocupado}>
            <Icon name="editar" />
            Editar
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onNuevoFlujo(e.id)} disabled={ocupado || vista.elementos.length < 2}>
            <Icon name="flujo" />
            Agregar flujo
          </button>
          {e.pendiente_revision ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => onConfirmar(seleccion)} disabled={ocupado}>
              <Icon name="check" />
              Confirmar
            </button>
          ) : null}
          <button type="button" className="icon-btn" onClick={() => onEliminarElemento(e)} disabled={ocupado} aria-label={`Eliminar ${e.nombre}`} title="Eliminar">
            <Icon name="basura" />
          </button>
        </div>
        <dl className={s.ficha}>
          {e.descripcion ? <div><dt>Descripción</dt><dd>{e.descripcion}</dd></div> : null}
          <div><dt>País de alojamiento</dt><dd>{e.derivados.pais_efectivo ? nombrePais(catalogo, e.derivados.pais_efectivo) : <span className={s.sinDato}>Sin informar</span>}{!e.pais && e.derivados.pais_efectivo ? " (se asume)" : ""}</dd></div>
          {e.proveedor ? <div><dt>{e.tipo === "tercero" ? "Razón social o marca" : "Proveedor"}</dt><dd>{e.proveedor}</dd></div> : null}
          <div><dt>Responsable interno</dt><dd>{e.responsable ?? <span className={s.sinDato}>Sin asignar</span>}</dd></div>
          {e.tipo === "tercero" ? (
            <>
              <div><dt>Rol</dt><dd>{nombreOpcion(catalogo.roles_tercero, e.rol_tercero)}</dd></div>
              <div><dt>Contrato de tratamiento</dt><dd>{e.contrato_firmado === true ? "Firmado" : e.contrato_firmado === false ? "Sin contrato" : "Por confirmar"}</dd></div>
            </>
          ) : null}
          <div><dt>Datos personales</dt><dd><Etiquetas catalogo={catalogo} codigos={e.categorias_datos} modo="datos" /></dd></div>
          <div><dt>Titulares</dt><dd><Etiquetas catalogo={catalogo} codigos={e.categorias_titulares} modo="titulares" /></dd></div>
          <div><dt>Registro</dt><dd>{ETIQUETA_ORIGEN[e.origen]} · actualizado {fechaHoraChile(e.fecha_actualizacion)}</dd></div>
        </dl>
        <Vinculos titulo="Envía datos a" flujos={salientes} campo="destino_id" porId={porId} onElegir={onSeleccionar} />
        <Vinculos titulo="Recibe datos de" flujos={entrantes} campo="origen_id" porId={porId} onElegir={onSeleccionar} />
        <Riesgos lista={lista} />
      </aside>
    );
  }

  const f = vista.flujos.find((x) => x.id === seleccion.id);
  if (!f) return null;
  const o = porId.get(f.origen_id);
  const d = porId.get(f.destino_id);
  const lista = riesgos(seleccion);
  return (
    <aside className={`card ${s.detalle}`} aria-label="Ficha del flujo">
      <div className={s.detalleCabeza}>
        <span className={s.detalleTipo} style={{ color: "var(--text-muted)" }}>
          <Icon name="flujo" />
          Flujo de datos
        </span>
        <h2 className={s.detalleTitulo}>
          {o?.nombre ?? "?"} → {d?.nombre ?? "?"}
        </h2>
        <ul className={s.etiquetas}>
          {f.derivados.internacional ? <li className={s.etiqueta} data-tono="internacional">Transferencia internacional</li> : null}
          {f.derivados.hacia_tercero ? <li className={s.etiqueta}>Hacia un tercero</li> : null}
          {f.derivados.sensibles.length ? <li className={s.etiqueta} data-tono="sensible">Datos sensibles</li> : null}
          {f.incluye_nna ? <li className={s.etiqueta} data-tono="nna">Niños, niñas y adolescentes</li> : null}
          {f.pendiente_revision ? <li className={s.etiqueta} data-tono="pendiente">Por confirmar</li> : null}
        </ul>
      </div>
      <div className={s.acciones}>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => onEditarFlujo(f)} disabled={ocupado}>
          <Icon name="editar" />
          Editar
        </button>
        {f.pendiente_revision ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onConfirmar(seleccion)} disabled={ocupado}>
            <Icon name="check" />
            Confirmar
          </button>
        ) : null}
        <button type="button" className="icon-btn" onClick={() => onEliminarFlujo(f)} disabled={ocupado} aria-label="Eliminar flujo" title="Eliminar">
          <Icon name="basura" />
        </button>
      </div>
      <dl className={s.ficha}>
        <div><dt>Finalidad</dt><dd>{f.finalidad ?? <span className={s.sinDato}>Sin informar</span>}</dd></div>
        <div>
          <dt>Recorrido</dt>
          <dd>
            {nombrePais(catalogo, f.derivados.pais_origen)} → {nombrePais(catalogo, f.derivados.pais_destino)}
          </dd>
        </div>
        {f.derivados.internacional ? (
          <div>
            <dt>Garantía de la transferencia</dt>
            <dd style={{ color: f.derivados.garantia_valida ? undefined : "var(--critico)" }}>
              {f.garantia ? nombreOpcion(catalogo.garantias, f.garantia) : "Sin informar"}
            </dd>
          </div>
        ) : null}
        <div><dt>Datos que viajan</dt><dd><Etiquetas catalogo={catalogo} codigos={f.categorias_datos} modo="datos" /></dd></div>
        <div><dt>Titulares</dt><dd><Etiquetas catalogo={catalogo} codigos={f.categorias_titulares} modo="titulares" /></dd></div>
        <div><dt>Frecuencia y medio</dt><dd>{nombreOpcion(catalogo.frecuencias, f.frecuencia)} · {nombreOpcion(catalogo.medios, f.medio)}</dd></div>
        <div><dt>Cifrado</dt><dd>{f.cifrado === true ? "Sí" : f.cifrado === false ? "No" : "No se sabe"}</dd></div>
        <div><dt>Registro</dt><dd>{ETIQUETA_ORIGEN[f.origen]} · actualizado {fechaHoraChile(f.fecha_actualizacion)}</dd></div>
      </dl>
      <ul className={s.vinculos} aria-label="Extremos del flujo">
        {[o, d].map((x, i) =>
          x ? (
            <li key={`${x.id}-${i}`}>
              <button type="button" className={s.vinculo} onClick={() => onSeleccionar({ tipo: "elemento", id: x.id })}>
                <Icon name={ICONO[x.tipo]} />
                <span>{i === 0 ? "Origen" : "Destino"}: {x.nombre}</span>
              </button>
            </li>
          ) : null,
        )}
      </ul>
      <Riesgos lista={lista} />
    </aside>
  );
}

function Vinculos({ titulo, flujos, campo, porId, onElegir }: {
  titulo: string;
  flujos: FlujoMapa[];
  campo: "origen_id" | "destino_id";
  porId: Map<number, ElementoMapa>;
  onElegir: (s: Seleccion) => void;
}) {
  if (!flujos.length) return null;
  return (
    <section style={{ display: "grid", gap: 6 }}>
      <h3 className="field-label">{titulo} ({flujos.length})</h3>
      <ul className={s.vinculos}>
        {flujos.map((f) => {
          const otro = porId.get(f[campo]);
          return (
            <li key={f.id}>
              <button type="button" className={s.vinculo} onClick={() => onElegir({ tipo: "flujo", id: f.id })}>
                <Icon name={f.derivados.internacional ? "globo" : "flujo"} />
                <span>{otro?.nombre ?? "?"}{f.finalidad ? ` · ${f.finalidad}` : ""}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Riesgos({ lista }: { lista: HallazgoMapa[] }) {
  if (!lista.length) return null;
  return (
    <section style={{ display: "grid", gap: 8 }}>
      <h3 className="field-label">Riesgos detectados ({lista.length})</h3>
      <ul className={s.hallazgos}>
        {lista.map((h) => (
          <li key={h.codigo} className={s.hallazgo} data-sev={h.severidad} style={{ padding: "10px 12px 10px 16px" }}>
            <span className={s.sev} data-sev={h.severidad}>{h.severidad}</span>
            <strong style={{ fontSize: "var(--fs-sm)" }}>{h.titulo}</strong>
            <p className={s.queHacer}>{h.recomendacion}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
