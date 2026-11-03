"use client";

/**
 * HU-16 · /empresa/borradores — borradores de cumplimiento adaptados por el Agente IA.
 *
 *   C1  Elegir la plantilla (Política de uso de LLM, Aviso de privacidad, PIA) y generar el
 *       borrador; se edita en Markdown y se descarga en Markdown o PDF.
 *   C2  El backend lo ajusta a la Ley 21.719 y a las brechas y dimensiones de la evaluación
 *       más reciente; con "Adaptar con el Agente IA" además lo redacta para el rubro y las
 *       instrucciones de la empresa.
 *   C3  Revisión y edición (con vista previa y los campos [COMPLETAR] pendientes), descarga
 *       previa y, al final, "Consolidar": queda de solo lectura y su PDF pasa a Mis documentos.
 *
 * La vista previa pinta el Markdown como texto con React (lib/borradores.ts): lo que escribe
 * el usuario nunca se inserta como HTML. HU-30: sin contrato vigente la página lo explica.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { ErrorBff } from "@/lib/encuesta/cliente";
import { fechaCorta } from "@/lib/empresa";
import { descargarBlob } from "@/lib/exportar";
import {
  advertenciasVisibles, cargarBorrador, cargarCatalogoBorradores, consolidarBorrador, cuotaBorradoresTexto,
  descargarBorrador, descartarBorrador, ETIQUETA_ESTADO, ETIQUETA_TIPO, generarBorrador, guardarBorrador,
  listarBorradores, parsearMarkdown, pendientesDe, segmentos, siguientePendiente, validarContenido,
  type BloqueMd, type BorradorApi, type CatalogoBorradoresApi, type FormatoBorrador, type TipoBorrador,
} from "@/lib/borradores";
import { useEspacioEmpresa } from "./EspacioEmpresaContexto";
import s from "@/components/admin/admin.module.css";
import b from "./borradores.module.css";

type Carga = { tipo: "cargando" } | { tipo: "listo" } | { tipo: "error"; mensaje: string };

function mensaje(e: unknown, porDefecto: string): string {
  return e instanceof ErrorBff && e.info.mensaje ? e.info.mensaje : porDefecto;
}

export function Borradores() {
  const espacio = useEspacioEmpresa();
  const router = useRouter();
  const [carga, setCarga] = useState<Carga>({ tipo: "cargando" });
  const [catalogo, setCatalogo] = useState<CatalogoBorradoresApi | null>(null);
  const [lista, setLista] = useState<BorradorApi[]>([]);
  const [abierto, setAbierto] = useState<BorradorApi | null>(null);
  const [aviso, setAviso] = useState("");

  const recargarLista = useCallback(async () => {
    setLista((await listarBorradores()).items);
  }, []);

  useEffect(() => {
    if (espacio.tipo !== "listo") return;
    Promise.all([cargarCatalogoBorradores(), listarBorradores()])
      .then(([cat, l]) => {
        setCatalogo(cat);
        setLista(l.items);
        setCarga({ tipo: "listo" });
      })
      .catch((e) => {
        if (e instanceof ErrorBff && e.status === 401) {
          router.replace("/ingresar?motivo=sesion");
          return;
        }
        setCarga({ tipo: "error", mensaje: mensaje(e, "No pudimos cargar tus borradores. Inténtalo de nuevo.") });
      });
  }, [espacio.tipo, router]);

  async function abrir(id: number) {
    try {
      setAbierto((await cargarBorrador(id)).borrador);
      requestAnimationFrame(() => document.getElementById("editor-borrador")?.scrollIntoView({ block: "start" }));
    } catch (e) {
      setAviso(mensaje(e, "No pudimos abrir el borrador."));
    }
  }

  const encabezado = (
    <header className="page-head">
      <div>
        <span className="eyebrow">Mi empresa</span>
        <h1 className="page-title">Borradores de cumplimiento</h1>
        <p className="page-sub">
          Genera la política de uso de IA, el aviso de privacidad o la evaluación de impacto de tu empresa, ajustados a la
          Ley 21.719 y a las brechas de tu última evaluación. Revísalos, edítalos y descárgalos antes de consolidarlos.
        </p>
      </div>
    </header>
  );

  if (espacio.tipo === "cargando" || (espacio.tipo === "listo" && carga.tipo === "cargando")) {
    return (
      <>
        {encabezado}
        <div className="skeleton" style={{ height: 240 }} role="status" aria-label="Cargando tus borradores" />
      </>
    );
  }
  if (espacio.tipo === "error" || carga.tipo === "error") {
    return (
      <>
        {encabezado}
        <div className={s.alerta} role="alert">
          <strong>{espacio.tipo === "error" ? espacio.mensaje : carga.tipo === "error" ? carga.mensaje : ""}</strong>
        </div>
      </>
    );
  }
  if (espacio.tipo === "sin_servicio") {
    return (
      <>
        {encabezado}
        <p className="callout" role="status">
          Los borradores son parte del servicio contratado y el de tu empresa no está activo.{" "}
          {espacio.contrato.contrato.documentos_disponibles ? (
            <>Tus borradores consolidados siguen en <Link href="/empresa/documentos">Mis documentos</Link>.</>
          ) : (
            "Contacta a Therion Labs para renovarlo."
          )}
        </p>
      </>
    );
  }

  return (
    <>
      {encabezado}
      {catalogo ? (
        <GenerarBorrador
          catalogo={catalogo}
          enRevision={lista.filter((x) => x.estado === "en_revision").length}
          alGenerar={async (borrador, avisoIa, cuota) => {
            setCatalogo({ ...catalogo, cuota });
            setAbierto(borrador);
            setAviso(avisoIa ?? `Generamos el borrador: ${ETIQUETA_TIPO[borrador.tipo]}.`);
            await recargarLista().catch(() => undefined);
            requestAnimationFrame(() => document.getElementById("editor-borrador")?.scrollIntoView({ block: "start" }));
          }}
        />
      ) : null}

      <ListaBorradores
        items={lista}
        abierto={abierto?.id ?? null}
        alAbrir={abrir}
        alDescartar={async (x) => {
          try {
            await descartarBorrador(x.id);
            if (abierto?.id === x.id) setAbierto(null);
            setAviso(`Descartamos el borrador ${ETIQUETA_TIPO[x.tipo]}.`);
            await recargarLista();
          } catch (e) {
            setAviso(mensaje(e, "No pudimos descartar el borrador."));
          }
        }}
      />

      {abierto && catalogo ? (
        <EditorBorrador
          key={abierto.id}
          borrador={abierto}
          maxCaracteres={catalogo.max_caracteres_contenido}
          alCambiar={async (nuevo) => {
            setAbierto(nuevo);
            await recargarLista().catch(() => undefined);
          }}
          alCerrar={() => setAbierto(null)}
        />
      ) : null}

      <p className="sr-only" role="status" aria-live="polite">{aviso}</p>
      {aviso ? <p className="callout" role="status" aria-hidden="true">{aviso}</p> : null}
    </>
  );
}

/* ================================================================== generar (C1 y C2) */
function GenerarBorrador({
  catalogo, enRevision, alGenerar,
}: {
  catalogo: CatalogoBorradoresApi;
  enRevision: number;
  alGenerar: (b: BorradorApi, aviso: string | undefined, cuota: CatalogoBorradoresApi["cuota"]) => Promise<void>;
}) {
  const [tipo, setTipo] = useState<TipoBorrador>(catalogo.plantillas[0]?.tipo ?? "politica_llm");
  const [instrucciones, setInstrucciones] = useState("");
  const [usarIa, setUsarIa] = useState(catalogo.ia_habilitada);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const max = catalogo.max_caracteres_instrucciones;
  const lleno = enRevision >= catalogo.max_en_revision;
  const plantilla = catalogo.plantillas.find((p) => p.tipo === tipo);

  async function generar(ev: FormEvent) {
    ev.preventDefault();
    if (ocupado || lleno) return;
    if (instrucciones.length > max) {
      setError(`Las instrucciones superan los ${max} caracteres.`);
      return;
    }
    setOcupado(true);
    setError("");
    try {
      const r = await generarBorrador(tipo, instrucciones, usarIa && catalogo.ia_habilitada);
      setInstrucciones("");
      await alGenerar(r.borrador, r.aviso, r.cuota);
    } catch (e) {
      setError(mensaje(e, "No pudimos generar el borrador. Inténtalo de nuevo."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <section className="card" aria-labelledby="titulo-generar">
      <div className="card-head">
        <div>
          <h2 id="titulo-generar" className="card-title">Nuevo borrador</h2>
          <p className="card-sub">Cada borrador parte de la evaluación más reciente de tu empresa.</p>
        </div>
      </div>
      <form className={b.generar} onSubmit={generar} aria-busy={ocupado}>
        <fieldset className={b.plantillas}>
          <legend>Documento</legend>
          {catalogo.plantillas.map((p) => (
            <label key={p.tipo} className={b.plantilla}>
              <input type="radio" name="plantilla" value={p.tipo} checked={tipo === p.tipo} onChange={() => setTipo(p.tipo)} />
              <strong>{ETIQUETA_TIPO[p.tipo]}</strong>
              <p>{p.descripcion}</p>
              <span className={b.dimensiones} aria-label="Dimensiones que cubre">
                {p.dimensiones.map((d) => <span key={d} className="badge tone-info">{d}</span>)}
              </span>
            </label>
          ))}
        </fieldset>

        {plantilla ? (
          <p className={s.sub}>
            {plantilla.secciones.length} secciones: {plantilla.secciones.slice(0, 5).join(", ")}
            {plantilla.secciones.length > 5 ? "…" : "."}
          </p>
        ) : null}

        <div className="field">
          <label className="field-label" htmlFor="instrucciones-borrador">
            Indicaciones para el Agente IA <span className="field-opcional">(opcional)</span>
          </label>
          <textarea
            id="instrucciones-borrador"
            className="input"
            rows={3}
            value={instrucciones}
            maxLength={max}
            disabled={!usarIa || !catalogo.ia_habilitada}
            onChange={(e) => setInstrucciones(e.target.value)}
            placeholder="Ej.: somos una clínica que usa un chatbot para agendar horas y un proveedor de IA en la nube."
            aria-describedby="ayuda-instrucciones"
          />
          <span id="ayuda-instrucciones" className="field-ayuda">
            Describe tu operación y cómo usan la IA. No escribas datos personales: se anonimizan antes de llegar al
            Agente IA y quedarán como campos por completar.
          </span>
          <span className={b.contador} aria-live="off">{instrucciones.length} / {max}</span>
        </div>

        <div className={b.fila}>
          <label className="check">
            <input
              type="checkbox"
              checked={usarIa && catalogo.ia_habilitada}
              disabled={!catalogo.ia_habilitada}
              onChange={(e) => setUsarIa(e.target.checked)}
            />
            <span>
              Adaptar con el Agente IA
              <span className={s.sub}>
                {catalogo.ia_habilitada ? cuotaBorradoresTexto(catalogo.cuota) : "El Agente IA no está habilitado."}
              </span>
            </span>
          </label>
          <button type="submit" className="btn btn-primary" disabled={ocupado || lleno} aria-busy={ocupado}>
            {ocupado ? "Generando…" : "Generar borrador"}
          </button>
        </div>
        {ocupado && usarIa ? (
          <p className={b.espera} role="status">El Agente IA está redactando tu borrador. Puede tardar hasta un minuto.</p>
        ) : null}
        {lleno ? (
          <p className="callout" role="status">
            Tienes {enRevision} borradores en revisión. Consolida o descarta alguno para generar otro.
          </p>
        ) : null}
        {error ? <div className={s.alerta} role="alert"><strong>{error}</strong></div> : null}
      </form>
    </section>
  );
}

/* ================================================================== lista */
function ListaBorradores({
  items, abierto, alAbrir, alDescartar,
}: {
  items: BorradorApi[];
  abierto: number | null;
  alAbrir: (id: number) => void;
  alDescartar: (b: BorradorApi) => Promise<void>;
}) {
  const [confirmar, setConfirmar] = useState<number | null>(null);
  const [ocupado, setOcupado] = useState<number | null>(null);

  return (
    <section className="card" aria-labelledby="titulo-mis-borradores">
      <div className="card-head">
        <div>
          <h2 id="titulo-mis-borradores" className="card-title">Mis borradores</h2>
          <p className="card-sub">
            Los consolidados quedan de solo lectura y su PDF está en <Link href="/empresa/documentos">Mis documentos</Link>.
          </p>
        </div>
      </div>
      {!items.length ? (
        <p className={s.vacio}>Aún no tienes borradores. Elige un documento y genera el primero.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Borradores de tu empresa</caption>
            <thead>
              <tr>
                <th scope="col">Documento</th>
                <th scope="col">Estado</th>
                <th scope="col">Actualizado</th>
                <th scope="col"><span className="sr-only">Acciones</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.id} aria-current={abierto === x.id ? "true" : undefined}>
                  <th scope="row">
                    {ETIQUETA_TIPO[x.tipo]}
                    <span className={s.sub}>
                      Versión {x.version}
                      {x.adaptado_ia ? " · adaptado con IA" : ""}
                      {x.pendientes ? ` · ${x.pendientes} campos por completar` : ""}
                    </span>
                  </th>
                  <td><span className={`badge tone-${ETIQUETA_ESTADO[x.estado].tono}`}>{ETIQUETA_ESTADO[x.estado].texto}</span></td>
                  <td>{fechaCorta(x.fecha_actualizacion)}</td>
                  <td>
                    {confirmar === x.id ? (
                      <div className={s.acciones} role="group" aria-label="Confirmar el descarte">
                        <span className={s.sub}>
                          ¿Descartar?{x.estado === "consolidado" ? " El PDF sigue en Mis documentos." : " Se pierden los cambios."}
                        </span>
                        <button
                          type="button"
                          className="btn btn-sm"
                          style={{ borderColor: "var(--alto)", color: "var(--alto)" }}
                          disabled={ocupado !== null}
                          aria-busy={ocupado === x.id}
                          onClick={async () => {
                            setOcupado(x.id);
                            await alDescartar(x);
                            setOcupado(null);
                            setConfirmar(null);
                          }}
                        >
                          Sí, descartar
                        </button>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmar(null)}>Cancelar</button>
                      </div>
                    ) : (
                      <div className={s.acciones}>
                        <button type="button" className="btn btn-sm" onClick={() => alAbrir(x.id)}
                                aria-label={`${x.editable ? "Revisar" : "Ver"} ${ETIQUETA_TIPO[x.tipo]}`}>
                          {x.editable ? "Revisar" : "Ver"}
                        </button>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmar(x.id)}
                                aria-label={`Descartar ${ETIQUETA_TIPO[x.tipo]}`}>
                          Descartar
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/* ================================================================== editor (C3) */
function EditorBorrador({
  borrador, maxCaracteres, alCambiar, alCerrar,
}: {
  borrador: BorradorApi;
  maxCaracteres: number;
  alCambiar: (b: BorradorApi) => Promise<void>;
  alCerrar: () => void;
}) {
  const [texto, setTexto] = useState(borrador.contenido ?? "");
  const [guardado, setGuardado] = useState(borrador.contenido ?? "");
  const [version, setVersion] = useState(borrador.version);
  const [vista, setVista] = useState<"editar" | "previa">("editar");
  const [ocupado, setOcupado] = useState<"guardar" | "md" | "pdf" | "consolidar" | null>(null);
  const [mensajeEditor, setMensajeEditor] = useState("");
  const [error, setError] = useState("");
  const [consolidando, setConsolidando] = useState(false);
  const [confirmarPendientes, setConfirmarPendientes] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);

  const editable = borrador.editable;
  const sucio = texto !== guardado;
  const pendientes = useMemo(() => pendientesDe(texto), [texto]);
  const bloques = useMemo(() => parsearMarkdown(texto), [texto]);
  const validacion = validarContenido(texto, maxCaracteres);
  const advertencias = advertenciasVisibles(borrador.advertencias);

  // Cambios sin guardar: el navegador avisa antes de salir
  useEffect(() => {
    if (!sucio) return;
    const antes = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", antes);
    return () => window.removeEventListener("beforeunload", antes);
  }, [sucio]);

  async function guardar(): Promise<boolean> {
    if (!validacion.ok) {
      setError(validacion.motivo ?? "");
      return false;
    }
    setOcupado("guardar");
    setError("");
    try {
      const r = await guardarBorrador(borrador.id, texto, version);
      setGuardado(r.borrador.contenido ?? texto);
      setTexto(r.borrador.contenido ?? texto);
      setVersion(r.borrador.version);
      setMensajeEditor(`Guardamos la versión ${r.borrador.version}.`);
      await alCambiar(r.borrador);
      return true;
    } catch (e) {
      setError(mensaje(e, "No pudimos guardar los cambios."));
      return false;
    } finally {
      setOcupado(null);
    }
  }

  async function descargar(formato: FormatoBorrador) {
    if (sucio && editable && !(await guardar())) return;
    setOcupado(formato);
    try {
      const { blob, nombre } = await descargarBorrador(borrador.id, formato);
      descargarBlob(blob, nombre);
      setMensajeEditor(`Descargamos ${nombre}.`);
    } catch (e) {
      setError(mensaje(e, "No pudimos descargar el borrador."));
    } finally {
      setOcupado(null);
    }
  }

  async function consolidar() {
    if (sucio && !(await guardar())) return;
    setOcupado("consolidar");
    setError("");
    try {
      const r = await consolidarBorrador(borrador.id, version, confirmarPendientes);
      setConsolidando(false);
      setMensajeEditor(`Consolidamos el borrador. Su PDF (${r.documento.nombre}) está en Mis documentos.`);
      await alCambiar(r.borrador);
    } catch (e) {
      setError(mensaje(e, "No pudimos consolidar el borrador."));
    } finally {
      setOcupado(null);
    }
  }

  function irAlPendiente() {
    const el = area.current;
    if (!el) return;
    setVista("editar");
    const pos = siguientePendiente(texto, el.selectionEnd);
    if (!pos) return;
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(pos.inicio, pos.fin);
    });
  }

  const estado = ETIQUETA_ESTADO[borrador.estado];

  return (
    <section id="editor-borrador" className="card" aria-labelledby="titulo-editor" style={{ scrollMarginTop: 16 }}>
      <div className={b.editor}>
        <div className={b.cabeza}>
          <div>
            <h2 id="titulo-editor" className="card-title">{borrador.titulo}</h2>
            <div className={b.metas}>
              <span className={`badge tone-${estado.tono}`}>{estado.texto}</span>
              <span>Versión {version}</span>
              {borrador.adaptado_ia ? <span className="badge tone-info">Adaptado con IA</span> : null}
              <span>· {fechaCorta(borrador.fecha_creacion)}</span>
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={alCerrar}>Cerrar</button>
        </div>

        {!editable ? (
          <p className="callout" role="status">
            Este borrador está consolidado: es de solo lectura. Su PDF está en{" "}
            <Link href="/empresa/documentos">Mis documentos</Link>. Para cambiarlo, genera uno nuevo.
          </p>
        ) : null}

        {advertencias.length ? (
          <div className="callout callout-aviso" role="note">
            <ul className={b.notas}>{advertencias.map((a) => <li key={a}>{a}</li>)}</ul>
          </div>
        ) : null}

        {borrador.notas.length && editable ? (
          <div className="callout" role="note">
            <strong>El Agente IA sugiere revisar:</strong>
            <ul className={b.notas}>{borrador.notas.map((n) => <li key={n}>{n}</li>)}</ul>
          </div>
        ) : null}

        {editable ? (
          <div className={b.pendientes} aria-live="polite">
            {pendientes.length ? (
              <>
                <span className="badge tone-medio">{pendientes.length} campos por completar</span>
                <button type="button" className="btn btn-ghost btn-sm" onClick={irAlPendiente}>
                  Ir al siguiente
                </button>
                <span className={s.sub}>Reemplaza cada [COMPLETAR: …] por el dato de tu empresa.</span>
              </>
            ) : (
              <span className="badge tone-ok">Sin campos por completar</span>
            )}
          </div>
        ) : null}

        <div className={`${s.pestanas} ${b.pestanasEditor}`} role="tablist" aria-label="Modo del editor">
          {(["editar", "previa"] as const).map((v) => (
            <button key={v} type="button" role="tab" aria-selected={vista === v} className={s.pestana}
                    aria-controls={`panel-${v}`} id={`tab-${v}`} onClick={() => setVista(v)}>
              {v === "editar" ? (editable ? "Editar" : "Markdown") : "Vista previa"}
            </button>
          ))}
        </div>

        <div className={b.paneles}>
          <div id="panel-editar" className={`${b.panel} ${vista === "editar" ? "" : b.oculto}`}>
            <label className={b.panelTitulo} htmlFor="contenido-borrador">Markdown</label>
            <textarea
              id="contenido-borrador"
              ref={area}
              className={b.texto}
              value={texto}
              readOnly={!editable}
              spellCheck
              onChange={(e) => setTexto(e.target.value)}
              aria-describedby="ayuda-markdown"
            />
            <span id="ayuda-markdown" className={s.sub}>
              {texto.length.toLocaleString("es-CL")} / {maxCaracteres.toLocaleString("es-CL")} caracteres · # títulos,
              - viñetas, **negrita**, tablas con |.
            </span>
          </div>
          <div id="panel-previa" className={`${b.panel} ${vista === "previa" ? "" : b.oculto}`}>
            <span className={b.panelTitulo}>Vista previa</span>
            <div className={b.vista} aria-label="Vista previa del borrador">
              <VistaPrevia bloques={bloques} />
            </div>
          </div>
        </div>

        <div className={b.acciones}>
          {editable ? (
            <button type="button" className="btn btn-primary" onClick={guardar}
                    disabled={!sucio || ocupado !== null} aria-busy={ocupado === "guardar"}>
              {ocupado === "guardar" ? "Guardando…" : sucio ? "Guardar cambios" : "Guardado"}
            </button>
          ) : null}
          <button type="button" className="btn" onClick={() => descargar("pdf")} disabled={ocupado !== null}
                  aria-busy={ocupado === "pdf"}>
            Descargar PDF
          </button>
          <button type="button" className="btn" onClick={() => descargar("md")} disabled={ocupado !== null}
                  aria-busy={ocupado === "md"}>
            Descargar Markdown
          </button>
          {editable && !consolidando ? (
            <button type="button" className="btn btn-ghost" onClick={() => setConsolidando(true)} disabled={ocupado !== null}>
              Consolidar…
            </button>
          ) : null}
        </div>

        {editable && consolidando ? (
          <div className={b.consolidar} role="group" aria-labelledby="titulo-consolidar">
            <strong id="titulo-consolidar">Consolidar el borrador</strong>
            <p className={s.sub} style={{ margin: 0 }}>
              Queda de solo lectura y su PDF final (sin la marca «BORRADOR») se guarda en Mis documentos.
              {sucio ? " Antes guardaremos tus cambios." : ""}
            </p>
            {pendientes.length ? (
              <label className="check">
                <input type="checkbox" checked={confirmarPendientes} onChange={(e) => setConfirmarPendientes(e.target.checked)} />
                <span>Consolidar aunque queden {pendientes.length} campos por completar</span>
              </label>
            ) : null}
            <div className={b.acciones}>
              <button type="button" className="btn btn-primary" onClick={consolidar}
                      disabled={ocupado !== null || (pendientes.length > 0 && !confirmarPendientes)}
                      aria-busy={ocupado === "consolidar"}>
                {ocupado === "consolidar" ? "Consolidando…" : "Sí, consolidar"}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setConsolidando(false)}>Cancelar</button>
            </div>
          </div>
        ) : null}

        {error ? <div className={s.alerta} role="alert"><strong>{error}</strong></div> : null}
        <p className="sr-only" role="status" aria-live="polite">{mensajeEditor}</p>
        {mensajeEditor && !error ? <p className={s.sub} aria-hidden="true">{mensajeEditor}</p> : null}
      </div>
    </section>
  );
}

/* ================================================================== vista previa segura */
function EnLinea({ texto }: { texto: string }) {
  return (
    <>
      {segmentos(texto).map((g, i) => {
        if (g.tipo === "negrita") return <strong key={i}>{g.texto}</strong>;
        if (g.tipo === "cursiva") return <em key={i}>{g.texto}</em>;
        if (g.tipo === "codigo") return <code key={i}>{g.texto}</code>;
        if (g.tipo === "pendiente") return <mark key={i} className={b.pendiente}>{g.texto}</mark>;
        return <span key={i}>{g.texto}</span>;
      })}
    </>
  );
}

function VistaPrevia({ bloques }: { bloques: BloqueMd[] }) {
  if (!bloques.length) return <p className={s.sub}>El borrador está vacío.</p>;
  return (
    <>
      {bloques.map((x, i) => {
        switch (x.tipo) {
          case "titulo": {
            // h1 del documento → h3 en la página (la página ya tiene su h1 y el h2 del editor)
            const Tag = x.nivel === 1 ? "h3" : x.nivel === 2 ? "h4" : "h5";
            return <Tag key={i}><EnLinea texto={x.texto} /></Tag>;
          }
          case "parrafo":
            return <p key={i}><EnLinea texto={x.texto} /></p>;
          case "cita":
            return <blockquote key={i}><EnLinea texto={x.texto} /></blockquote>;
          case "separador":
            return <hr key={i} />;
          case "lista": {
            const Lista = x.ordenada ? "ol" : "ul";
            return <Lista key={i}>{x.items.map((t, j) => <li key={j}><EnLinea texto={t} /></li>)}</Lista>;
          }
          case "tabla":
            return (
              <div key={i} className="table-wrap">
                <table>
                  <thead><tr>{x.cabecera.map((c, j) => <th key={j} scope="col"><EnLinea texto={c} /></th>)}</tr></thead>
                  <tbody>
                    {x.filas.map((f, j) => (
                      <tr key={j}>{f.map((c, k) => <td key={k}><EnLinea texto={c} /></td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </>
  );
}
