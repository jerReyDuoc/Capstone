"use client";

/**
 * Pasos del formulario de una actividad de tratamiento:
 *   1 La actividad                 nombre, descripción, área, finalidades y rol de la empresa
 *   2 Sistemas y datos             elegir del mapa sistemas, bases, terceros y flujos (y qué datos usa)
 *   3 Origen y licitud             fuentes (si alguna es de acceso público) y base de licitud
 *   4 Destinatarios                terceros y transferencias internacionales (vienen del mapa)
 *   5 Conservación y decisiones    plazo por categoría de datos y decisiones automatizadas
 *   6 Seguridad y revisión         medidas de seguridad y lo que falta para dejarla vigente
 *
 * Cada paso edita el borrador local; DetalleActividad lo guarda (solo lo que cambió).
 */
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";
import ms from "@/components/empresa/mapa/mapa.module.css";
import {
  ETIQUETA_TIPO_PLURAL, nombreDato, nombreOpcion, nombrePais, nombreTitular, plural,
  type CatalogoMapa, type ElementoMapa, type FlujoMapa, type TipoElemento, type VistaMapa,
} from "@/lib/mapaDatos";
import {
  alinearPlazos, aplicarPlazoATodas, nombreFlujo, seleccionInicial, vistaPreviaDesdeMapa,
  type CatalogoRat, type CodigoCampo, type Completitud, type ContenidoActividad, type Plazo, type Seleccion,
} from "@/lib/registroActividades";
import s from "./rat.module.css";

export type Previa = ReturnType<typeof vistaPreviaDesdeMapa>;

export interface PropsPaso {
  borrador: ContenidoActividad;
  cambiar: (parcial: Partial<ContenidoActividad>) => void;
  catalogo: CatalogoRat;
  catalogoMapa: CatalogoMapa | null;
  mapa: VistaMapa;
  completitud: Completitud;
  previa: Previa;
  errorCampo: { campo: string; mensaje: string } | null;
}

/* ============================================================ piezas */

function Bloque({
  codigo,
  catalogo,
  completitud,
  children,
  titulo,
}: {
  codigo?: CodigoCampo;
  catalogo: CatalogoRat;
  completitud: Completitud;
  children: ReactNode;
  titulo?: string;
}) {
  const campo = codigo ? catalogo.campos.find((c) => c.codigo === codigo) : undefined;
  const estado = codigo ? completitud.campos?.[codigo] : undefined;
  const idTitulo = useId();
  return (
    <section className={`card ${s.bloque}`} aria-labelledby={idTitulo}>
      <div className={s.bloqueCabeza}>
        <h3 id={idTitulo} className={s.bloqueTitulo}>
          {titulo ?? campo?.titulo}
          {campo?.desde_mapa ? (
            <span className={s.desdeMapa}><Icon name="mapa" />Desde el mapa</span>
          ) : null}
          {estado ? (
            <span className={s.estadoCampo} data-completo={estado.completo}>
              {estado.completo ? (estado.aplica ? "Completo" : "No aplica") : "Pendiente"}
            </span>
          ) : null}
        </h3>
        {campo ? <p className={ms.ayuda} style={{ fontSize: "var(--fs-sm)" }}>{campo.ayuda}</p> : null}
        {estado && !estado.completo && estado.faltante ? (
          <p className={ms.ayuda} style={{ color: "var(--medio)", fontWeight: 600 }}>{estado.faltante}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function ErrorCampo({ error, campos }: { error: PropsPaso["errorCampo"]; campos: string[] }) {
  if (!error || !campos.includes(error.campo)) return null;
  return <p className={ms.error} role="alert">{error.mensaje}</p>;
}

function Etiquetas({ items, vacio = "Sin datos todavía" }: { items: { texto: string; tono?: string }[]; vacio?: string }) {
  if (!items.length) return <span className={ms.sinDato}>{vacio}</span>;
  return (
    <ul className={ms.etiquetas}>
      {items.map((x) => (
        <li key={x.texto} className={ms.etiqueta} data-tono={x.tono}>{x.texto}</li>
      ))}
    </ul>
  );
}

function ListaTextos({
  valores,
  onCambiar,
  etiquetaAgregar,
  placeholder,
  maximo,
  maxLargo,
  idBase,
}: {
  valores: string[];
  onCambiar: (v: string[]) => void;
  etiquetaAgregar: string;
  placeholder: string;
  maximo: number;
  maxLargo: number;
  idBase: string;
}) {
  const [nuevo, setNuevo] = useState("");
  const agregar = () => {
    const v = nuevo.trim();
    if (!v || valores.some((x) => x.toLowerCase() === v.toLowerCase())) return;
    onCambiar([...valores, v]);
    setNuevo("");
  };
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {valores.length ? (
        <ol className={s.listaEditable}>
          {valores.map((v, i) => (
            <li key={i} className={s.itemEditable}>
              <input
                className={ms.control}
                value={v}
                maxLength={maxLargo}
                aria-label={`Finalidad ${i + 1}`}
                onChange={(e) => onCambiar(valores.map((x, j) => (j === i ? e.target.value : x)))}
              />
              <button type="button" className="icon-btn" aria-label={`Quitar la finalidad ${i + 1}`} onClick={() => onCambiar(valores.filter((_, j) => j !== i))}>
                <Icon name="basura" />
              </button>
            </li>
          ))}
        </ol>
      ) : null}
      {valores.length < maximo ? (
        <div className={s.agregar}>
          <input
            id={`${idBase}-nuevo`}
            className={ms.control}
            value={nuevo}
            maxLength={maxLargo}
            placeholder={placeholder}
            aria-label={etiquetaAgregar}
            onChange={(e) => setNuevo(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                agregar();
              }
            }}
          />
          <button type="button" className="btn btn-ghost" onClick={agregar} disabled={!nuevo.trim()}>
            <Icon name="mas" />
            Agregar
          </button>
        </div>
      ) : null}
    </div>
  );
}

function OpcionesRadio({
  nombre,
  opciones,
  valor,
  onCambiar,
}: {
  nombre: string;
  opciones: { codigo: string; nombre: string; descripcion?: string; referencia?: string }[];
  valor: string | null;
  onCambiar: (v: string) => void;
}) {
  return (
    <div className={s.opciones} role="radiogroup">
      {opciones.map((o) => (
        <label key={o.codigo} className={s.opcion}>
          <input type="radio" name={nombre} checked={valor === o.codigo} onChange={() => onCambiar(o.codigo)} />
          <strong>{o.nombre}</strong>
          {o.descripcion ? <small>{o.descripcion}</small> : null}
          {o.referencia ? <em>{o.referencia}</em> : null}
        </label>
      ))}
    </div>
  );
}

function SiNo({ nombre, valor, onCambiar, si = "Sí", no = "No" }: {
  nombre: string;
  valor: boolean | null;
  onCambiar: (v: boolean) => void;
  si?: string;
  no?: string;
}) {
  return (
    <div className={`${ms.segmentado} ${ms.dos}`} role="radiogroup">
      <label className={ms.segmento}>
        <input type="radio" name={nombre} checked={valor === true} onChange={() => onCambiar(true)} />
        <Icon name="check" />
        {si}
      </label>
      <label className={ms.segmento}>
        <input type="radio" name={nombre} checked={valor === false} onChange={() => onCambiar(false)} />
        <Icon name="cerrar" />
        {no}
      </label>
    </div>
  );
}

/* ============================================================ 1. La actividad */

export function PasoActividad({ borrador: b, cambiar, catalogo, completitud, errorCampo }: PropsPaso) {
  const id = useId();
  return (
    <>
      <Bloque catalogo={catalogo} completitud={completitud} titulo="Identificación">
        <div className={ms.rejilla}>
          <div className={`${ms.campo} ${ms.ancho}`}>
            <label htmlFor={`${id}-nombre`}>Nombre de la actividad<span className={ms.obligatorio} aria-hidden>*</span></label>
            <input id={`${id}-nombre`} className={ms.control} value={b.nombre} maxLength={150} onChange={(e) => cambiar({ nombre: e.target.value })} aria-invalid={errorCampo?.campo === "nombre" || undefined} />
            <ErrorCampo error={errorCampo} campos={["nombre"]} />
          </div>
          <div className={`${ms.campo} ${ms.ancho}`}>
            <label htmlFor={`${id}-desc`}>Descripción</label>
            <textarea id={`${id}-desc`} className={ms.control} value={b.descripcion ?? ""} maxLength={1000} onChange={(e) => cambiar({ descripcion: e.target.value })} />
            <span className={ms.ayuda}>Opcional. En qué consiste la actividad, en pocas palabras.</span>
            <ErrorCampo error={errorCampo} campos={["descripcion"]} />
          </div>
          <div className={ms.campo}>
            <label htmlFor={`${id}-area`}>Área responsable</label>
            <input id={`${id}-area`} className={ms.control} value={b.area ?? ""} maxLength={120} placeholder="Por ejemplo, Gerencia de Personas" onChange={(e) => cambiar({ area: e.target.value })} aria-invalid={errorCampo?.campo === "area" || undefined} />
            <span className={ms.ayuda}>Un cargo o un área, sin datos de contacto de personas.</span>
            <ErrorCampo error={errorCampo} campos={["area"]} />
          </div>
        </div>
      </Bloque>

      <Bloque codigo="finalidades" catalogo={catalogo} completitud={completitud}>
        <ListaTextos
          valores={b.finalidades}
          onCambiar={(v) => cambiar({ finalidades: v })}
          etiquetaAgregar="Nueva finalidad"
          placeholder="Por ejemplo, calcular y pagar las remuneraciones"
          maximo={15}
          maxLargo={300}
          idBase={`${id}-fin`}
        />
        <ErrorCampo error={errorCampo} campos={["finalidades"]} />
      </Bloque>

      <Bloque codigo="rol" catalogo={catalogo} completitud={completitud}>
        <OpcionesRadio nombre={`${id}-rol`} opciones={catalogo.roles_empresa} valor={b.rol} onCambiar={(v) => cambiar({ rol: v })} />
        {b.rol === "encargado" ? (
          <div className={ms.campo}>
            <label htmlFor={`${id}-mandante`}>¿Por cuenta de qué organización?<span className={ms.obligatorio} aria-hidden>*</span></label>
            <input id={`${id}-mandante`} className={ms.control} value={b.responsable_mandante ?? ""} maxLength={150} onChange={(e) => cambiar({ responsable_mandante: e.target.value })} />
            <span className={ms.ayuda}>La organización que decide sobre el tratamiento (tu cliente o mandante).</span>
            <ErrorCampo error={errorCampo} campos={["responsable_mandante"]} />
          </div>
        ) : null}
      </Bloque>
    </>
  );
}

/* ============================================================ 2. Sistemas y datos */

function ItemMapa({
  titulo,
  subtitulo,
  disponiblesDatos,
  disponiblesTitulares,
  seleccion,
  onElegir,
  onCambiar,
  catalogoMapa,
  etiquetas,
}: {
  titulo: string;
  subtitulo: string;
  disponiblesDatos: string[];
  disponiblesTitulares: string[];
  seleccion: Seleccion | undefined;
  onElegir: (elegido: boolean) => void;
  onCambiar: (s: Seleccion) => void;
  catalogoMapa: CatalogoMapa | null;
  etiquetas?: ReactNode;
}) {
  const id = useId();
  const alternar = (lista: string[], c: string) => (lista.includes(c) ? lista.filter((x) => x !== c) : [...lista, c]);
  return (
    <li className={s.itemMapa} data-elegido={Boolean(seleccion) || undefined}>
      <div className={s.itemMapaCabeza}>
        <label>
          <input type="checkbox" checked={Boolean(seleccion)} onChange={(e) => onElegir(e.target.checked)} />
          <span style={{ minWidth: 0 }}>
            {titulo}
            <span className={ms.ayuda} style={{ display: "block", fontWeight: 400 }}>{subtitulo}</span>
          </span>
        </label>
        {etiquetas}
      </div>
      {seleccion ? (
        <div className={s.itemMapaDetalle}>
          <fieldset>
            <legend>¿Qué datos usa esta actividad?</legend>
            {disponiblesDatos.length ? (
              <div className={ms.opcionesCategoria}>
                {disponiblesDatos.map((c) => {
                  const sensible = catalogoMapa?.categorias_datos.find((x) => x.codigo === c)?.sensible ?? false;
                  return (
                    <label key={c} className={ms.pastilla} data-sensible={sensible || undefined}>
                      <input type="checkbox" checked={seleccion.categorias_datos.includes(c)} onChange={() => onCambiar({ ...seleccion, categorias_datos: alternar(seleccion.categorias_datos, c) })} />
                      {nombreDato(catalogoMapa, c)}
                      {sensible ? <span className={ms.marcaSensible}>SENSIBLE</span> : null}
                    </label>
                  );
                })}
              </div>
            ) : (
              <span className={ms.sinDato}>El mapa no registra categorías de datos aquí. Agrégalas en el mapa.</span>
            )}
          </fieldset>
          <fieldset>
            <legend>¿De quiénes?</legend>
            {disponiblesTitulares.length ? (
              <div className={ms.opcionesCategoria}>
                {disponiblesTitulares.map((t) => {
                  const nna = catalogoMapa?.categorias_titulares.find((x) => x.codigo === t)?.nna ?? false;
                  return (
                    <label key={t} className={ms.pastilla}>
                      <input type="checkbox" checked={seleccion.categorias_titulares.includes(t)} onChange={() => onCambiar({ ...seleccion, categorias_titulares: alternar(seleccion.categorias_titulares, t) })} />
                      {nombreTitular(catalogoMapa, t)}
                      {nna ? <span className={ms.marcaNna} title="Niños, niñas y adolescentes">NNA</span> : null}
                    </label>
                  );
                })}
              </div>
            ) : (
              <span className={ms.sinDato}>El mapa no registra de quiénes son estos datos. Agrégalo en el mapa.</span>
            )}
          </fieldset>
          <span className={ms.ayuda} id={`${id}-nota`}>Solo se ofrecen los datos que el mapa registra. Para agregar otros, edítalos en el mapa.</span>
        </div>
      ) : null}
    </li>
  );
}

export function PasoSistemas({ borrador: b, cambiar, catalogo, catalogoMapa, mapa, completitud, previa, errorCampo }: PropsPaso) {
  const porId = new Map<number, ElementoMapa>(mapa.elementos.map((e) => [e.id, e]));
  const elegidoE = new Map(b.elementos.map((x) => [x.id, x]));
  const elegidoF = new Map(b.flujos.map((x) => [x.id, x]));
  const grupos: TipoElemento[] = ["sistema", "base_datos", "tercero"];

  const elegirElemento = (e: ElementoMapa, si: boolean) =>
    cambiar({ elementos: si ? [...b.elementos, seleccionInicial(e)] : b.elementos.filter((x) => x.id !== e.id) });
  const cambiarElemento = (sel: Seleccion) => cambiar({ elementos: b.elementos.map((x) => (x.id === sel.id ? sel : x)) });
  const elegirFlujo = (f: FlujoMapa, si: boolean) =>
    cambiar({ flujos: si ? [...b.flujos, seleccionInicial(f)] : b.flujos.filter((x) => x.id !== f.id) });
  const cambiarFlujo = (sel: Seleccion) => cambiar({ flujos: b.flujos.map((x) => (x.id === sel.id ? sel : x)) });

  const faltantesMapa = [...b.elementos.filter((x) => !porId.has(x.id)), ...b.flujos.filter((x) => !mapa.flujos.some((f) => f.id === x.id))];

  if (!mapa.elementos.length) {
    return (
      <Bloque codigo="bases_datos" catalogo={catalogo} completitud={completitud}>
        <p className="callout callout-aviso">
          <Icon name="mapa" />
          <span>
            Tu mapa de datos está vacío. Registra allí los sistemas, bases de datos y terceros, y vuelve para elegirlos.{" "}
            <Link href="/empresa/mapa-datos">Ir al mapa de datos</Link>
          </span>
        </p>
      </Bloque>
    );
  }

  return (
    <>
      <Bloque codigo="bases_datos" catalogo={catalogo} completitud={completitud}>
        {faltantesMapa.length ? (
          <div className={ms.alertaInfo} role="alert">
            <Icon name="alerta" />
            <span>
              {plural(faltantesMapa.length, "elemento elegido ya no está", "elementos elegidos ya no están")} en el mapa.{" "}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => cambiar({
                  elementos: b.elementos.filter((x) => porId.has(x.id)),
                  flujos: b.flujos.filter((x) => mapa.flujos.some((f) => f.id === x.id)),
                })}
              >
                Quitarlos de la actividad
              </button>
            </span>
          </div>
        ) : null}
        {grupos.map((tipo) => {
          const lista = mapa.elementos.filter((e) => e.tipo === tipo).sort((x, y) => x.nombre.localeCompare(y.nombre, "es"));
          if (!lista.length) return null;
          return (
            <div key={tipo} className={s.grupoMapa}>
              <h4 style={{ fontSize: "var(--fs-xs)", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                {ETIQUETA_TIPO_PLURAL[tipo]}
              </h4>
              <ul className={s.listaEditable}>
                {lista.map((e) => (
                  <ItemMapa
                    key={e.id}
                    titulo={e.nombre}
                    subtitulo={[nombrePais(catalogoMapa, e.derivados.pais_efectivo), e.proveedor].filter(Boolean).join(" · ")}
                    disponiblesDatos={e.categorias_datos}
                    disponiblesTitulares={e.categorias_titulares}
                    seleccion={elegidoE.get(e.id)}
                    onElegir={(si) => elegirElemento(e, si)}
                    onCambiar={cambiarElemento}
                    catalogoMapa={catalogoMapa}
                    etiquetas={e.derivados.sensibles.length ? <span className={ms.etiqueta} data-tono="sensible">Datos sensibles</span> : null}
                  />
                ))}
              </ul>
            </div>
          );
        })}
        <ErrorCampo error={errorCampo} campos={["elementos"]} />
      </Bloque>

      <Bloque catalogo={catalogo} completitud={completitud} titulo="Flujos de datos">
        <p className={ms.ayuda} style={{ fontSize: "var(--fs-sm)" }}>
          Elige los envíos de datos que forman parte de la actividad. Los terceros que los reciben y las transferencias
          internacionales se suman solos.
        </p>
        {mapa.flujos.length ? (
          <ul className={s.listaEditable}>
            {mapa.flujos.map((f) => (
              <ItemMapa
                key={f.id}
                titulo={nombreFlujo(f, porId)}
                subtitulo={f.finalidad ?? "Sin finalidad registrada en el mapa"}
                disponiblesDatos={f.categorias_datos}
                disponiblesTitulares={f.categorias_titulares}
                seleccion={elegidoF.get(f.id)}
                onElegir={(si) => elegirFlujo(f, si)}
                onCambiar={cambiarFlujo}
                catalogoMapa={catalogoMapa}
                etiquetas={f.derivados.internacional ? (
                  <span className={ms.etiqueta} data-tono="internacional">Sale de Chile</span>
                ) : null}
              />
            ))}
          </ul>
        ) : (
          <span className={ms.sinDato}>El mapa todavía no tiene flujos.</span>
        )}
        <ErrorCampo error={errorCampo} campos={["flujos"]} />
      </Bloque>

      <section className={s.previa} aria-label="Lo que la actividad toma del mapa">
        <strong style={{ fontSize: "var(--fs-sm)" }}>Así queda con lo que elegiste</strong>
        <dl>
          <div>
            <dt>Tipos de datos</dt>
            <dd>
              <Etiquetas items={previa.tiposDatos.map((c) => ({
                texto: nombreDato(catalogoMapa, c),
                tono: catalogoMapa?.categorias_datos.find((x) => x.codigo === c)?.sensible ? "sensible" : undefined,
              }))} />
            </dd>
          </div>
          <div>
            <dt>Titulares</dt>
            <dd>
              <Etiquetas items={previa.titulares.map((t) => ({
                texto: nombreTitular(catalogoMapa, t),
                tono: catalogoMapa?.categorias_titulares.find((x) => x.codigo === t)?.nna ? "nna" : undefined,
              }))} />
            </dd>
          </div>
          <div>
            <dt>Ámbito territorial</dt>
            <dd><Etiquetas items={previa.paises.map((p) => ({ texto: nombrePais(catalogoMapa, p), tono: p !== "CL" ? "internacional" : undefined }))} /></dd>
          </div>
          <div>
            <dt>Terceros destinatarios</dt>
            <dd><Etiquetas items={previa.terceros.map((t) => ({ texto: t }))} vacio="Ninguno" /></dd>
          </div>
        </dl>
        {previa.haySensibles ? (
          <p className={ms.alertaInfo}><Icon name="candado" /><span>La actividad usa datos sensibles: en el paso 3 te pediremos la base que permite tratarlos.</span></p>
        ) : null}
        {previa.incluyeNna ? (
          <p className={ms.alertaInfo} data-tono="nna"><Icon name="usuario" /><span>Incluye datos de niños, niñas o adolescentes: su interés superior debe guiar el tratamiento.</span></p>
        ) : null}
      </section>

      <Bloque catalogo={catalogo} completitud={completitud} titulo="Aclaración del ámbito territorial">
        <div className={ms.campo}>
          <label htmlFor="rat-ambito-nota">Nota (opcional)</label>
          <input id="rat-ambito-nota" className={ms.control} value={b.ambito_nota ?? ""} maxLength={300} placeholder="Por ejemplo, clientes de Chile y Perú" onChange={(e) => cambiar({ ambito_nota: e.target.value })} />
          <ErrorCampo error={errorCampo} campos={["ambito_nota"]} />
        </div>
      </Bloque>
    </>
  );
}

/* ============================================================ 3. Origen y licitud */

export function PasoLicitud({ borrador: b, cambiar, catalogo, completitud, previa, errorCampo }: PropsPaso) {
  const id = useId();
  const [nuevoTipo, setNuevoTipo] = useState("");
  const publica = new Set(catalogo.fuentes.filter((f) => f.acceso_publico).map((f) => f.codigo));
  return (
    <>
      <Bloque codigo="fuentes" catalogo={catalogo} completitud={completitud}>
        {b.fuentes.length ? (
          <ul className={s.listaEditable}>
            {b.fuentes.map((f, i) => (
              <li key={i} className={s.itemFuente}>
                <select className={`select ${ms.control}`} value={f.tipo} aria-label={`Tipo de la fuente ${i + 1}`} onChange={(e) => cambiar({ fuentes: b.fuentes.map((x, j) => (j === i ? { ...x, tipo: e.target.value } : x)) })}>
                  {catalogo.fuentes.map((o) => <option key={o.codigo} value={o.codigo}>{o.nombre}</option>)}
                </select>
                <input
                  className={ms.control}
                  value={f.detalle ?? ""}
                  maxLength={300}
                  placeholder={f.tipo === "otro" ? "Describe la fuente (obligatorio)" : "Detalle (opcional)"}
                  aria-label={`Detalle de la fuente ${i + 1}`}
                  onChange={(e) => cambiar({ fuentes: b.fuentes.map((x, j) => (j === i ? { ...x, detalle: e.target.value } : x)) })}
                />
                <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  {publica.has(f.tipo) ? <span className={ms.etiqueta} data-tono="ok">Acceso público</span> : null}
                  <button type="button" className="icon-btn" aria-label={`Quitar la fuente ${i + 1}`} onClick={() => cambiar({ fuentes: b.fuentes.filter((_, j) => j !== i) })}>
                    <Icon name="basura" />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        <div className={s.agregar}>
          <select className={`select ${ms.control}`} value={nuevoTipo} aria-label="Nueva fuente" onChange={(e) => setNuevoTipo(e.target.value)}>
            <option value="">Elige de dónde vienen los datos…</option>
            {catalogo.fuentes.map((o) => <option key={o.codigo} value={o.codigo}>{o.nombre}</option>)}
          </select>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={!nuevoTipo}
            onClick={() => {
              cambiar({ fuentes: [...b.fuentes, { tipo: nuevoTipo, detalle: null }] });
              setNuevoTipo("");
            }}
          >
            <Icon name="mas" />
            Agregar fuente
          </button>
        </div>
        {nuevoTipo ? <span className={ms.ayuda}>{catalogo.fuentes.find((f) => f.codigo === nuevoTipo)?.descripcion}</span> : null}
        <ErrorCampo error={errorCampo} campos={["fuentes"]} />
      </Bloque>

      <Bloque codigo="base_licitud" catalogo={catalogo} completitud={completitud}>
        <OpcionesRadio nombre={`${id}-base`} opciones={catalogo.bases_licitud} valor={b.base_licitud} onCambiar={(v) => cambiar({ base_licitud: v })} />
        {b.base_licitud === "interes_legitimo" ? (
          <div className={ms.campo}>
            <label htmlFor={`${id}-interes`}>Describe el interés legítimo<span className={ms.obligatorio} aria-hidden>*</span></label>
            <textarea id={`${id}-interes`} className={ms.control} value={b.interes_legitimo ?? ""} maxLength={1500} onChange={(e) => cambiar({ interes_legitimo: e.target.value })} />
            <span className={ms.ayuda}>Qué interés concreto persigue tu empresa y por qué no prevalece sobre los derechos de las personas.</span>
            <ErrorCampo error={errorCampo} campos={["interes_legitimo"]} />
          </div>
        ) : null}
        {previa.haySensibles ? (
          <div className={ms.campo}>
            <span className={ms.etiquetaCampo}>Base para los datos sensibles<span className={ms.obligatorio} aria-hidden>*</span></span>
            <span className={ms.ayuda}>La actividad usa datos sensibles. Para ellos, la regla general es el consentimiento expreso; elige la base que aplica.</span>
            <OpcionesRadio nombre={`${id}-sensibles`} opciones={catalogo.bases_sensibles} valor={b.base_sensibles} onCambiar={(v) => cambiar({ base_sensibles: v })} />
          </div>
        ) : null}
        <ErrorCampo error={errorCampo} campos={["base_licitud", "base_sensibles"]} />
      </Bloque>
    </>
  );
}

/* ============================================================ 4. Destinatarios y transferencias */

export function PasoDestinatarios({ borrador: b, cambiar, catalogo, catalogoMapa, mapa, completitud, previa }: PropsPaso) {
  const porId = new Map<number, ElementoMapa>(mapa.elementos.map((e) => [e.id, e]));
  const terceros = [...new Set([
    ...b.elementos.map((x) => porId.get(x.id)).filter((e): e is ElementoMapa => e?.tipo === "tercero"),
    ...b.flujos.map((x) => mapa.flujos.find((f) => f.id === x.id)).map((f) => (f ? porId.get(f.destino_id) : undefined))
      .filter((e): e is ElementoMapa => e?.tipo === "tercero"),
  ])];
  return (
    <>
      <Bloque codigo="destinatarios" catalogo={catalogo} completitud={completitud}>
        {terceros.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">Tercero</th><th scope="col">Rol</th><th scope="col">País</th><th scope="col">Contrato</th></tr></thead>
              <tbody>
                {terceros.map((t) => (
                  <tr key={t.id}>
                    <td>{t.nombre}</td>
                    <td>{t.rol_tercero ? nombreOpcion(catalogoMapa?.roles_tercero, t.rol_tercero) : "Sin informar"}</td>
                    <td>{nombrePais(catalogoMapa, t.derivados.pais_efectivo)}</td>
                    <td>{t.contrato_firmado ? "Firmado" : t.rol_tercero === "encargado" ? "Por revisar" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <label className={ms.casillaLinea}>
            <input type="checkbox" checked={b.sin_destinatarios} onChange={(e) => cambiar({ sin_destinatarios: e.target.checked })} />
            <span>Confirmo que los datos de esta actividad <strong>no se comunican ni se ceden a terceros</strong>.</span>
          </label>
        )}
        <span className={ms.ayuda}>
          ¿Falta un destinatario? Agrégalo en el <Link href="/empresa/mapa-datos">mapa de datos</Link> con su flujo y elígelo en el paso 2.
        </span>
      </Bloque>

      <Bloque codigo="transferencias" catalogo={catalogo} completitud={completitud}>
        {previa.transferencias.length ? (
          <ul className={s.checklist}>
            {previa.transferencias.map((t) => {
              const f = mapa.flujos.find((x) => x.id === t.flujo);
              return (
                <li key={t.flujo} className={s.check} data-completo={t.garantiaValida}>
                  <Icon name={t.garantiaValida ? "check" : "alerta"} />
                  <span>
                    {t.nombre} · {nombrePais(catalogoMapa, t.pais)}
                    <small>{t.garantiaValida
                      ? `Garantía: ${nombreOpcion(catalogoMapa?.garantias, f?.garantia ?? null)}`
                      : "Sin garantía documentada: regístrala en el flujo del mapa."}</small>
                  </span>
                  <Link className="btn btn-ghost btn-sm" href="/empresa/mapa-datos">Ver en el mapa</Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className={ms.ayuda} style={{ fontSize: "var(--fs-sm)" }}>
            {b.elementos.length || b.flujos.length
              ? "Con lo elegido, los datos de esta actividad no salen de Chile."
              : "Elige en el paso 2 los sistemas y flujos para saber si los datos salen de Chile."}
          </p>
        )}
        {completitud.advertencias?.filter((a) => a.includes("está en")).map((a) => (
          <p key={a} className={ms.alertaInfo}><Icon name="globo" /><span>{a}</span></p>
        ))}
      </Bloque>
    </>
  );
}

/* ============================================================ 5. Conservación y decisiones */

export function PasoConservacion({ borrador: b, cambiar, catalogo, catalogoMapa, completitud, previa, errorCampo }: PropsPaso) {
  const id = useId();
  const plazos = alinearPlazos(b.plazos, previa.tiposDatos);
  const cambiarPlazo = (i: number, parcial: Partial<Plazo>) =>
    cambiar({ plazos: plazos.map((p, j) => (j === i ? { ...p, ...parcial } : p)) });
  const d = b.decisiones;
  return (
    <>
      <Bloque codigo="conservacion" catalogo={catalogo} completitud={completitud}>
        {plazos.length ? (
          <>
            <div className="table-wrap">
              <table className={`table ${s.plazos}`}>
                <thead>
                  <tr>
                    <th scope="col">Categoría de datos</th>
                    <th scope="col">Plazo</th>
                    <th scope="col">Se cuenta</th>
                    <th scope="col">Fundamento (opcional)</th>
                  </tr>
                </thead>
                <tbody>
                  {plazos.map((p, i) => (
                    <tr key={p.categoria}>
                      <th scope="row" style={{ fontWeight: 600 }}>{nombreDato(catalogoMapa, p.categoria)}</th>
                      <td>
                        <span style={{ display: "flex", gap: 6 }}>
                          <input
                            className={`${ms.control} ${s.controlChico} ${s.plazoNumero}`}
                            type="number"
                            min={1}
                            max={p.unidad ? catalogo.max_plazo[p.unidad] : undefined}
                            inputMode="numeric"
                            aria-label={`Plazo de ${nombreDato(catalogoMapa, p.categoria)}`}
                            value={p.plazo ?? ""}
                            onChange={(e) => cambiarPlazo(i, { plazo: e.target.value ? Math.max(1, Math.trunc(Number(e.target.value))) : null })}
                          />
                          <select className={`select ${ms.control} ${s.controlChico}`} aria-label={`Unidad del plazo de ${nombreDato(catalogoMapa, p.categoria)}`} value={p.unidad ?? ""} onChange={(e) => cambiarPlazo(i, { unidad: e.target.value || null })}>
                            <option value="">Unidad…</option>
                            {catalogo.unidades_plazo.map((u) => <option key={u.codigo} value={u.codigo}>{u.nombre}</option>)}
                          </select>
                        </span>
                      </td>
                      <td>
                        <select className={`select ${ms.control} ${s.controlChico}`} aria-label={`Desde cuándo se cuenta el plazo de ${nombreDato(catalogoMapa, p.categoria)}`} value={p.desde ?? ""} onChange={(e) => cambiarPlazo(i, { desde: e.target.value || null })}>
                          <option value="">Sin indicar</option>
                          {catalogo.inicios_plazo.map((u) => <option key={u.codigo} value={u.codigo}>{u.nombre}</option>)}
                        </select>
                      </td>
                      <td>
                        <input className={`${ms.control} ${s.controlChico}`} maxLength={300} placeholder="Por ejemplo, Código del Trabajo" aria-label={`Fundamento del plazo de ${nombreDato(catalogoMapa, p.categoria)}`} value={p.fundamento ?? ""} onChange={(e) => cambiarPlazo(i, { fundamento: e.target.value })} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {plazos.length > 1 && plazos[0].plazo && plazos[0].unidad ? (
              <button type="button" className="btn btn-ghost btn-sm" style={{ justifySelf: "start" }} onClick={() => cambiar({ plazos: aplicarPlazoATodas(plazos, plazos[0]) })}>
                Usar el plazo de «{nombreDato(catalogoMapa, plazos[0].categoria)}» en todas
              </button>
            ) : null}
          </>
        ) : (
          <span className={ms.sinDato}>Elige en el paso 2 los datos de la actividad para indicar cuánto se guarda cada uno.</span>
        )}
        <ErrorCampo error={errorCampo} campos={["plazos"]} />
      </Bloque>

      <Bloque codigo="decisiones" catalogo={catalogo} completitud={completitud}>
        <div className={ms.campo}>
          <span className={ms.etiquetaCampo}>¿La actividad toma decisiones automatizadas o arma perfiles de las personas?</span>
          <SiNo nombre={`${id}-existe`} valor={d.existe} onCambiar={(v) => cambiar({ decisiones: { ...d, existe: v } })} />
        </div>
        {d.existe ? (
          <div className={ms.rejilla}>
            <label className={`${ms.casillaLinea} ${ms.ancho}`}>
              <input type="checkbox" checked={d.perfilamiento} onChange={(e) => cambiar({ decisiones: { ...d, perfilamiento: e.target.checked } })} />
              <span>Incluye perfilamiento (evaluar o predecir aspectos de las personas, como preferencias o comportamiento).</span>
            </label>
            <div className={`${ms.campo} ${ms.ancho}`}>
              <label htmlFor={`${id}-logica`}>Lógica que se aplica<span className={ms.obligatorio} aria-hidden>*</span></label>
              <textarea id={`${id}-logica`} className={ms.control} value={d.logica ?? ""} maxLength={1500} onChange={(e) => cambiar({ decisiones: { ...d, logica: e.target.value } })} />
              <span className={ms.ayuda}>Explica en lenguaje simple qué datos considera y cómo llega a la decisión (por ejemplo, un modelo de IA que puntúa solicitudes según su historial).</span>
            </div>
            <div className={`${ms.campo} ${ms.ancho}`}>
              <label htmlFor={`${id}-consec`}>Efectos para las personas (opcional)</label>
              <textarea id={`${id}-consec`} className={ms.control} value={d.consecuencias ?? ""} maxLength={1000} onChange={(e) => cambiar({ decisiones: { ...d, consecuencias: e.target.value } })} />
            </div>
            <div className={`${ms.campo} ${ms.ancho}`}>
              <span className={ms.etiquetaCampo}>¿Una persona puede revisar la decisión si el titular lo pide?</span>
              <SiNo nombre={`${id}-humana`} valor={d.intervencion_humana} onCambiar={(v) => cambiar({ decisiones: { ...d, intervencion_humana: v } })} />
            </div>
          </div>
        ) : null}
        <ErrorCampo error={errorCampo} campos={["decisiones"]} />
      </Bloque>
    </>
  );
}

/* ============================================================ 6. Seguridad y revisión */

export function PasoSeguridad({
  borrador: b,
  cambiar,
  catalogo,
  completitud,
  errorCampo,
  onIrAPaso,
  sinGuardar,
}: PropsPaso & { onIrAPaso: (paso: number) => void; sinGuardar: boolean }) {
  const id = useId();
  const elegidas = new Set(b.medidas.codigos);
  const alternar = (c: string) =>
    cambiar({ medidas: { ...b.medidas, codigos: elegidas.has(c) ? b.medidas.codigos.filter((x) => x !== c) : [...b.medidas.codigos, c] } });
  return (
    <>
      <Bloque codigo="medidas" catalogo={catalogo} completitud={completitud}>
        {catalogo.grupos_medidas.map((g) => (
          <fieldset key={g} className={ms.grupoCategorias}>
            <legend>{g}</legend>
            <div className={ms.opcionesCategoria}>
              {catalogo.medidas_seguridad.filter((m) => m.grupo === g).map((m) => (
                <label key={m.codigo} className={ms.pastilla}>
                  <input type="checkbox" checked={elegidas.has(m.codigo)} onChange={() => alternar(m.codigo)} />
                  {m.nombre}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        <div className={ms.campo}>
          <label htmlFor={`${id}-otras`}>Otras medidas (opcional)</label>
          <textarea id={`${id}-otras`} className={ms.control} value={b.medidas.otras ?? ""} maxLength={1000} onChange={(e) => cambiar({ medidas: { ...b.medidas, otras: e.target.value } })} />
        </div>
        <ErrorCampo error={errorCampo} campos={["medidas"]} />
      </Bloque>

      <Bloque catalogo={catalogo} completitud={completitud} titulo="Revisión antes de dejarla vigente">
        {sinGuardar ? (
          <p className={ms.alertaInfo}><Icon name="info" /><span>Tienes cambios sin guardar: guárdalos para actualizar esta revisión.</span></p>
        ) : null}
        <p className={ms.ayuda} style={{ fontSize: "var(--fs-sm)" }}>
          {completitud.puede_quedar_vigente
            ? "Está todo lo obligatorio. Envíala a revisión y luego déjala vigente: esa versión quedará fija como respaldo."
            : `Faltan ${plural(completitud.faltantes.length, "dato obligatorio", "datos obligatorios")} para poder dejarla vigente.`}
        </p>
        <ul className={s.checklist}>
          {catalogo.campos.map((c) => {
            const e = completitud.campos?.[c.codigo];
            const completo = Boolean(e?.completo);
            return (
              <li key={c.codigo} className={s.check} data-completo={completo}>
                <Icon name={completo ? "check" : "alerta"} />
                <span>
                  {c.titulo}
                  {!completo && e?.faltante ? <small>{e.faltante}</small> : e && !e.aplica ? <small>No aplica</small> : null}
                </span>
                {!completo ? (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => onIrAPaso(c.paso)}>Ir al paso {c.paso}</button>
                ) : <span />}
              </li>
            );
          })}
        </ul>
        {completitud.advertencias?.length ? (
          <div style={{ display: "grid", gap: 8 }}>
            <strong style={{ fontSize: "var(--fs-sm)" }}>Recomendaciones</strong>
            {completitud.advertencias.map((a) => (
              <p key={a} className={ms.alertaInfo}><Icon name="info" /><span>{a}</span></p>
            ))}
          </div>
        ) : null}
      </Bloque>
    </>
  );
}
