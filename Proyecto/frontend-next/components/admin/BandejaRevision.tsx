"use client";

/**
 * HU-22 · Bandeja de revisión del Oficial de Cumplimiento (panel interno de Therion Labs).
 *
 * La pregunta con que el oficial entra es "¿qué decidió la IA que tengo que validar?". Por eso:
 *   - arriba, la verdad de referencia en una frase (cuánto coincide la IA con sus revisiones);
 *   - a la izquierda, la lista priorizada (seguridad, divergencias, sin resolver...);
 *   - a la derecha, la cadena de decisión del elemento abierto: lo que DECLARÓ la organización,
 *     lo que PROPUSO la IA y lo que queda VIGENTE, con el quiebre marcado donde no coinciden,
 *     y debajo el formulario para confirmar o corregir con comentario.
 * Al resolver, se abre solo el siguiente pendiente. Cada decisión queda en el audit log (backend).
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { comoErrorAdmin, type ErrorAdmin } from "@/lib/admin/api";
import {
  apiRevision,
  cadenaDecision,
  COMENTARIO_MAX,
  decisionDe,
  errorComentario,
  fechaCorta,
  FILTROS_INICIALES,
  largoComentario,
  MOTIVOS,
  NOMBRE_CLASIFICACION,
  NOMBRE_FUENTE,
  NOMBRE_ORIGEN_EVENTO,
  NOMBRE_RESOLUCION,
  nombreClasificacion,
  porcentaje,
  RESOLUTIVAS,
  siguientePendiente,
  sugerida,
  TEXTO_MOTIVO,
  textoBotonDecision,
  TONO_CLASIFICACION,
  TONO_MOTIVO,
  type Bandeja,
  type Clasificacion,
  type DetalleRespuesta,
  type FiltrosBandeja,
  type ItemEvento,
  type ItemRespuesta,
  type Motivo,
  type Resolucion,
  type Resolutiva,
  type ResumenReferencia,
} from "@/lib/admin/revision";
import { BarraAdmin } from "./BarraAdmin";
import a from "./admin.module.css";
import s from "./revision.module.css";

type Seleccion = { tipo: "respuesta" | "evento"; id: number } | null;

const AYUDA_OPCION: Record<Resolutiva, string> = {
  cumplido: "La evidencia demuestra el control completo",
  parcialmente_cumplido: "Existe, pero incompleto o sin aplicar en todo",
  no_cumplido: "No hay evidencia suficiente",
  no_aplica: "El control no corresponde a la organización",
};

export function BandejaRevision() {
  const router = useRouter();
  const [filtros, setFiltros] = useState<FiltrosBandeja>(FILTROS_INICIALES);
  const [bandeja, setBandeja] = useState<Bandeja | null>(null);
  const [resumen, setResumen] = useState<ResumenReferencia | null>(null);
  const [dominios, setDominios] = useState<{ id: number; nombre_dominio: string | null }[]>([]);
  const [seleccion, setSeleccion] = useState<Seleccion>(null);
  const [error, setError] = useState<ErrorAdmin | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  const manejarError = useCallback(
    (e: unknown): ErrorAdmin => {
      const err = comoErrorAdmin(e);
      if (err.codigo === "SESION_EXPIRADA") router.replace("/admin/login?motivo=sesion");
      return err;
    },
    [router],
  );

  const cargar = useCallback(
    async (f: FiltrosBandeja) => {
      setCargando(true);
      try {
        const b = await apiRevision.bandeja(f);
        setBandeja(b);
        return b;
      } catch (e) {
        setError(manejarError(e));
        return null;
      } finally {
        setCargando(false);
      }
    },
    [manejarError],
  );

  const cargarResumen = useCallback(async () => {
    try {
      setResumen(await apiRevision.resumen());
    } catch {
      /* la franja de referencia es secundaria: sin ella la bandeja sigue sirviendo */
    }
  }, []);

  useEffect(() => {
    void cargar(filtros);
  }, [cargar, filtros]);

  useEffect(() => {
    void cargarResumen();
    apiRevision.dominios().then(setDominios).catch(() => setDominios([]));
  }, [cargarResumen]);

  // Correcciones 05-11: botón "Actualizar" de la barra (y al volver a la pestaña del navegador)
  const actualizarTodo = useCallback(async () => {
    setError(null);
    await Promise.all([cargar(filtros), cargarResumen()]);
  }, [cargar, cargarResumen, filtros]);

  function cambiar(parcial: Partial<FiltrosBandeja>) {
    setSeleccion(null);
    setFiltros((f) => ({ ...f, page: 1, ...parcial }));
  }

  /** Tras una decisión: recarga y abre el siguiente pendiente de la misma lista. */
  async function alResolver(texto: string) {
    setAviso(texto);
    const items = (bandeja?.items ?? []) as { id: number; pendiente: boolean }[];
    const siguiente = seleccion ? siguientePendiente(items, seleccion.id) : null;
    const b = await cargar(filtros);
    void cargarResumen();
    const sigue = siguiente && b?.items.some((x) => x.id === siguiente.id);
    setSeleccion(sigue && seleccion ? { tipo: seleccion.tipo, id: siguiente.id } : null);
  }

  const pend = bandeja?.pendientes;

  return (
    <div className={`${a.pagina} ${s.raiz}`}>
      <BarraAdmin onActualizar={actualizarTodo} alVolver />

      <main id="contenido" className={a.contenido}>
        <div>
          <h1 className="page-title">Bandeja de revisión</h1>
          <p className="page-sub">
            Confirma o corrige lo que decidió la IA y resuelve los eventos de seguridad. Cada revisión fija la
            clasificación final, queda en el audit log y sirve para medir qué tan bien clasifica la IA.
          </p>
        </div>

        <FranjaReferencia resumen={resumen} />

        {aviso ? (
          <p className="callout" role="status">
            {aviso}{" "}
            <button type="button" className="link-btn" onClick={() => setAviso(null)}>Cerrar</button>
          </p>
        ) : null}
        {error ? (
          <div className={a.alerta} role="alert">
            <strong>{error.mensaje}</strong>
            <button type="button" className="link-btn" onClick={() => setError(null)}>Cerrar</button>
          </div>
        ) : null}

        <div className={s.pestanas} role="tablist" aria-label="Qué revisar">
          {([
            ["clasificaciones", "Clasificaciones", pend?.clasificaciones],
            ["eventos", "Eventos de seguridad", pend?.eventos],
          ] as const).map(([clave, texto, n]) => (
            <button key={clave} role="tab" type="button" className={s.pestana} aria-selected={filtros.vista === clave}
                    onClick={() => cambiar({ vista: clave, motivo: null })}>
              {texto}
              {n != null ? (
                <span className={`${s.cuenta} ${clave === "eventos" && n > 0 ? s.cuentaAlerta : ""}`}>
                  {n}<span className="sr-only"> pendientes</span>
                </span>
              ) : null}
            </button>
          ))}
        </div>

        <Filtros filtros={filtros} cambiar={cambiar} bandeja={bandeja} dominios={dominios} />

        <div className={s.paneles} data-abierto={seleccion ? "true" : "false"}>
          <div className={s.columnaLista}>
            {filtros.vista === "clasificaciones" ? (
              <ListaRespuestas items={(bandeja?.items ?? []) as ItemRespuesta[]} cargando={cargando && !bandeja}
                               filtros={filtros} seleccion={seleccion} abrir={(id) => setSeleccion({ tipo: "respuesta", id })} />
            ) : (
              <ListaEventos items={(bandeja?.items ?? []) as ItemEvento[]} cargando={cargando && !bandeja}
                            filtros={filtros} seleccion={seleccion} abrir={(id) => setSeleccion({ tipo: "evento", id })} />
            )}
            {bandeja && bandeja.pages > 1 ? (
              <nav className={s.paginacion} aria-label="Páginas de la bandeja">
                <button type="button" className="btn btn-ghost btn-sm" disabled={filtros.page <= 1}
                        onClick={() => setFiltros((f) => ({ ...f, page: f.page - 1 }))}>Anterior</button>
                <span>Página {bandeja.page} de {bandeja.pages} · {bandeja.total} en total</span>
                <button type="button" className="btn btn-ghost btn-sm" disabled={filtros.page >= bandeja.pages}
                        onClick={() => setFiltros((f) => ({ ...f, page: f.page + 1 }))}>Siguiente</button>
              </nav>
            ) : null}
          </div>

          <section className={s.detalle} aria-label="Elemento en revisión">
            {seleccion?.tipo === "respuesta" ? (
              <PanelRespuesta key={seleccion.id} id={seleccion.id} umbral={bandeja?.umbral_confianza ?? 0.8}
                              volver={() => setSeleccion(null)} onError={(e) => setError(manejarError(e))}
                              onResuelta={alResolver} />
            ) : seleccion?.tipo === "evento" ? (
              <PanelEvento key={seleccion.id}
                           evento={((bandeja?.items ?? []) as ItemEvento[]).find((x) => x.id === seleccion.id) ?? null}
                           volver={() => setSeleccion(null)} onError={(e) => setError(manejarError(e))}
                           onResuelto={alResolver}
                           irARespuesta={(rid) => {
                             setFiltros({ ...FILTROS_INICIALES, estado: "todas", vista: "clasificaciones" });
                             setSeleccion({ tipo: "respuesta", id: rid });
                           }} />
            ) : (
              <div className={s.vacio}>
                <strong>Elige un elemento de la lista</strong>
                <span>Verás lo que declaró la organización, lo que propuso la IA y podrás decidir.</span>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ verdad de referencia */
function FranjaReferencia({ resumen }: { resumen: ResumenReferencia | null }) {
  if (!resumen) return null;
  const p = resumen.precision_llm;
  const total = resumen.confirmadas + resumen.corregidas;
  const ev = resumen.eventos;
  return (
    <section className={s.referencia} aria-labelledby="titulo-referencia">
      <div>
        <h2 id="titulo-referencia" className="sr-only">Verdad de referencia</h2>
        {p.n_revisadas ? (
          <p className={s.referenciaFrase}>
            La IA coincidió con tu revisión en <span className={s.referenciaCifra}>{porcentaje(p.accuracy)}</span> de{" "}
            {p.n_revisadas} {p.n_revisadas === 1 ? "pregunta" : "preguntas"} que evaluó.
          </p>
        ) : (
          <p className={s.referenciaFrase}>Aún no hay revisiones sobre decisiones de la IA.</p>
        )}
        <p className={s.referenciaNota}>
          Es la verdad de referencia con que se mide el modelo (F1 macro {p.f1_macro == null ? "—" : p.f1_macro.toFixed(2)}).
          El detalle por clase está en las métricas de IA.
        </p>
      </div>
      <div className={s.balance}>
        {total ? (
          <div className={s.barra} role="img"
               aria-label={`${resumen.confirmadas} confirmadas y ${resumen.corregidas} corregidas`}>
            <span className={s.barraConfirmada} style={{ width: `${(resumen.confirmadas / total) * 100}%` }} />
            <span className={s.barraCorregida} style={{ width: `${(resumen.corregidas / total) * 100}%` }} />
          </div>
        ) : null}
        <ul className={s.leyenda}>
          <li><span className={s.punto} style={{ background: "var(--accent)" }} aria-hidden="true" />
            Confirmadas <strong>{resumen.confirmadas}</strong></li>
          <li><span className={s.punto} style={{ background: "var(--medio)" }} aria-hidden="true" />
            Corregidas <strong>{resumen.corregidas}</strong></li>
          <li><span className={s.punto} style={{ background: "var(--critico)" }} aria-hidden="true" />
            Ataques confirmados <strong>{ev.ataques_confirmados}</strong></li>
          <li><span className={s.punto} style={{ background: "var(--info)" }} aria-hidden="true" />
            Falsos positivos <strong>{ev.falsos_positivos}</strong></li>
        </ul>
        {ev.precision_deteccion != null ? (
          <p className={s.nota}>La detección de ataques acertó en {porcentaje(ev.precision_deteccion)} de los eventos resueltos.</p>
        ) : null}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ filtros */
function Filtros({ filtros, cambiar, bandeja, dominios }: {
  filtros: FiltrosBandeja; cambiar: (p: Partial<FiltrosBandeja>) => void; bandeja: Bandeja | null;
  dominios: { id: number; nombre_dominio: string | null }[];
}) {
  const idEval = useId();
  const [evaluacion, setEvaluacion] = useState(filtros.evaluacion_id ? String(filtros.evaluacion_id) : "");
  useEffect(() => {
    setEvaluacion(filtros.evaluacion_id ? String(filtros.evaluacion_id) : "");
  }, [filtros.evaluacion_id]);
  const conteo = bandeja?.pendientes.por_motivo;
  const esClasif = filtros.vista === "clasificaciones";
  return (
    <div className={s.filtros}>
      <div className={s.filaFiltros}>
        <div className={s.segmentado} role="group" aria-label="Estado de la revisión">
          {([["pendiente", "Pendientes"], ["revisada", "Revisadas"], ["todas", "Todas"]] as const).map(([v, t]) => (
            <button key={v} type="button" aria-pressed={filtros.estado === v} onClick={() => cambiar({ estado: v })}>{t}</button>
          ))}
        </div>
        <form className={s.campoFiltro} onSubmit={(e) => {
          e.preventDefault();
          const n = Number(evaluacion);
          cambiar({ evaluacion_id: Number.isInteger(n) && n > 0 ? n : null });
        }}>
          <label htmlFor={idEval}><span>Evaluación n.º</span></label>
          <input id={idEval} className={`${s.selector} ${s.numero}`} inputMode="numeric" pattern="[0-9]*"
                 value={evaluacion} placeholder="Todas"
                 onChange={(e) => setEvaluacion(e.target.value.replace(/\D/g, "").slice(0, 9))}
                 onBlur={() => {
                   const n = Number(evaluacion);
                   const nuevo = Number.isInteger(n) && n > 0 ? n : null;
                   if (nuevo !== filtros.evaluacion_id) cambiar({ evaluacion_id: nuevo });
                 }} />
        </form>
        {esClasif ? (
          <>
            <label className={s.campoFiltro}>
              <span>Dimensión</span>
              <select className={s.selector} value={filtros.dominio_id ?? ""}
                      onChange={(e) => cambiar({ dominio_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Todas</option>
                {dominios.map((d) => <option key={d.id} value={d.id}>{d.nombre_dominio ?? `Dimensión ${d.id}`}</option>)}
              </select>
            </label>
            <label className={s.campoFiltro}>
              <span>Criticidad</span>
              <select className={s.selector} value={filtros.criticidad ?? ""}
                      onChange={(e) => cambiar({ criticidad: e.target.value || null })}>
                <option value="">Todas</option>
                {["Crítica", "Alta", "Media", "Baja"].map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <label className={s.campoFiltro}>
              <span>Orden</span>
              <select className={s.selector} value={filtros.orden}
                      onChange={(e) => cambiar({ orden: e.target.value as FiltrosBandeja["orden"] })}>
                <option value="prioridad">Más urgente primero</option>
                <option value="reciente">Más reciente primero</option>
              </select>
            </label>
          </>
        ) : null}
      </div>
      {esClasif ? (
        <div className="chip-group" role="group" aria-label="Filtrar por motivo">
          <button type="button" className="chip" aria-pressed={!filtros.motivo} onClick={() => cambiar({ motivo: null })}>
            {filtros.estado === "pendiente" ? "Todo lo urgente" : "Todos los motivos"}
          </button>
          {MOTIVOS.map((mo) => (
            <button key={mo} type="button" className="chip" aria-pressed={filtros.motivo === mo}
                    title={TEXTO_MOTIVO[mo].ayuda} onClick={() => cambiar({ motivo: filtros.motivo === mo ? null : mo })}>
              {TEXTO_MOTIVO[mo].corto}
              {conteo && filtros.estado === "pendiente" ? <span> ({conteo[mo] ?? 0}<span className="sr-only"> pendientes</span>)</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ listas */
function Vacio({ filtros }: { filtros: FiltrosBandeja }) {
  const sinFiltros = !filtros.motivo && !filtros.evaluacion_id && !filtros.dominio_id && !filtros.criticidad;
  if (filtros.estado === "pendiente" && sinFiltros) {
    return (
      <div className={s.vacio}>
        <strong>{filtros.vista === "eventos" ? "No hay eventos por resolver" : "No hay clasificaciones por revisar"}</strong>
        <span>Cuando la IA o la capa de seguridad decidan algo que necesite tu revisión, aparecerá aquí.</span>
      </div>
    );
  }
  return (
    <div className={s.vacio}>
      <strong>Nada coincide con estos filtros</strong>
      <span>Prueba con otro motivo, otra evaluación o «Todas».</span>
    </div>
  );
}

function MiniCadena({ r }: { r: ItemRespuesta }) {
  const c = cadenaDecision(r);
  return (
    <span className={s.mini}>
      <span className={s.miniOrg}>{nombreClasificacion(c.declarado)}</span>
      {c.ia ? (
        <>
          <span className={c.quiebre ? s.miniDistinto : s.miniFlecha} aria-hidden="true">{c.quiebre ? "≠" : "="}</span>
          <span className={s.miniIa}>
            <span className="sr-only">{c.quiebre ? "la IA propuso, distinto: " : "la IA propuso, igual: "}</span>
            {nombreClasificacion(c.ia)}
          </span>
        </>
      ) : null}
    </span>
  );
}

function ListaRespuestas({ items, cargando, filtros, seleccion, abrir }: {
  items: ItemRespuesta[]; cargando: boolean; filtros: FiltrosBandeja; seleccion: Seleccion; abrir: (id: number) => void;
}) {
  if (cargando) return <p className={s.vacio}>Cargando la bandeja…</p>;
  if (!items.length) return <Vacio filtros={filtros} />;
  return (
    <ul className={s.lista} aria-label="Clasificaciones">
      {items.map((r) => (
        <li key={r.id}>
          <button type="button" className={s.fila} aria-current={seleccion?.tipo === "respuesta" && seleccion.id === r.id}
                  onClick={() => abrir(r.id)}>
            <span className={s.filaCabeza}>
              <span><span className={s.codigo}>{r.control.codigo ?? `Control ${r.control.id}`}</span>
                {r.control.dominio ? ` · ${r.control.dominio}` : ""}</span>
              <span>Evaluación {r.evaluacion.id}{r.evaluacion.empresa ? ` · ${r.evaluacion.empresa}` : ""}</span>
            </span>
            <span className={s.filaPregunta}>{r.control.pregunta ?? "Pregunta sin texto"}</span>
            <MiniCadena r={r} />
            <span className={s.filaMotivos}>
              {r.motivos.map((mo) => (
                <span key={mo} className={`badge tone-${TONO_MOTIVO[mo]}`}>{TEXTO_MOTIVO[mo].corto}</span>
              ))}
              {r.revision && !r.pendiente ? (
                <span className="badge tone-ok">
                  {r.revision.decision === "corregida" ? "Corregida" : r.revision.decision === "confirmada" ? "Confirmada" : "Revisada"}
                </span>
              ) : null}
              {r.revision && r.pendiente ? <span className="badge tone-medio">Cambió tras tu revisión</span> : null}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function ListaEventos({ items, cargando, filtros, seleccion, abrir }: {
  items: ItemEvento[]; cargando: boolean; filtros: FiltrosBandeja; seleccion: Seleccion; abrir: (id: number) => void;
}) {
  if (cargando) return <p className={s.vacio}>Cargando los eventos…</p>;
  if (!items.length) return <Vacio filtros={filtros} />;
  return (
    <ul className={s.lista} aria-label="Eventos de seguridad">
      {items.map((ev) => (
        <li key={ev.id}>
          <button type="button" className={s.fila} aria-current={seleccion?.tipo === "evento" && seleccion.id === ev.id}
                  onClick={() => abrir(ev.id)}>
            <span className={s.filaCabeza}>
              <span>{NOMBRE_ORIGEN_EVENTO[ev.origen] ?? ev.origen}</span>
              <span>{fechaCorta(ev.fecha)}{ev.evaluacion_id ? ` · Evaluación ${ev.evaluacion_id}` : ""}</span>
            </span>
            <span className={s.filaPregunta}>{ev.extracto ?? "Extracto eliminado por la política de retención"}</span>
            <span className={s.filaMotivos}>
              <span className="badge tone-alto">{ev.tipo.replace(/_/g, " ")}</span>
              {ev.revision?.resolucion ? (
                <span className={`badge tone-${ev.revision.resolucion === "falso_positivo" ? "info" : "ok"}`}>
                  {NOMBRE_RESOLUCION[ev.revision.resolucion]}
                </span>
              ) : ev.revision ? <span className="badge tone-info">Revisado sin veredicto</span> : null}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ detalle de una respuesta */
function CadenaDecision({ r, umbral }: { r: ItemRespuesta; umbral: number }) {
  const c = cadenaDecision(r);
  return (
    <ol className={s.cadena} aria-label="Cadena de decisión">
      <li className={s.eslabon}>
        <span className={s.voz}><span className={`${s.vozMarca} ${s.vozOrg}`} aria-hidden="true" />Declaró la organización</span>
        <span className={s.veredicto}>{nombreClasificacion(c.declarado)}</span>
      </li>
      <li className={`${s.eslabon} ${c.quiebre ? s.eslabonQuiebre : ""}`}>
        <span className={s.voz}><span className={`${s.vozMarca} ${s.vozIa}`} aria-hidden="true" />Propuso la IA</span>
        {c.ia ? (
          <>
            <span className={s.veredicto}>{nombreClasificacion(c.ia)}</span>
            {c.quiebre ? <span className="sr-only">No coincide con lo declarado.</span> : null}
          </>
        ) : (
          <span className={`${s.veredicto} ${s.veredictoVacio}`}>{r.motivos.includes("seguridad") ? "No se le envió" : "Sin evaluar"}</span>
        )}
        {c.confianza != null ? (
          <span className={s.confianza}>
            Confianza {porcentaje(c.confianza)} · umbral {porcentaje(umbral)}
            <span className={s.confianzaBarra} aria-hidden="true">
              <span style={{ width: `${Math.round(c.confianza * 100)}%` }} />
              <i style={{ left: `${Math.round(umbral * 100)}%` }} />
            </span>
          </span>
        ) : null}
      </li>
      <li className={s.eslabon}>
        <span className={s.voz}><span className={`${s.vozMarca} ${s.vozOficial}`} aria-hidden="true" />Vigente hoy</span>
        <span className={s.veredicto}>{nombreClasificacion(c.vigente)}</span>
        <span className={s.nota}>Según {NOMBRE_FUENTE[c.fuente ?? ""] ?? "lo declarado"}.</span>
      </li>
    </ol>
  );
}

function PanelRespuesta({ id, umbral, volver, onError, onResuelta }: {
  id: number; umbral: number; volver: () => void; onError: (e: unknown) => void; onResuelta: (texto: string) => void;
}) {
  const [d, setD] = useState<DetalleRespuesta | null>(null);
  const [elegida, setElegida] = useState<Resolutiva | null>(null);
  const [comentario, setComentario] = useState("");
  const [intento, setIntento] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const titulo = useRef<HTMLHeadingElement>(null);
  const idComentario = useId();
  const idAyuda = useId();
  // onError llega como función nueva en cada render: se guarda en una ref para no recargar en bucle
  const errorRef = useRef(onError);
  errorRef.current = onError;

  useEffect(() => {
    let vivo = true;
    apiRevision.detalle(id).then((x) => {
      if (!vivo) return;
      setD(x);
      setElegida(sugerida(x));
      titulo.current?.focus();
    }).catch((e) => vivo && errorRef.current(e));
    return () => { vivo = false; };
  }, [id]);

  const errComentario = useMemo(() => errorComentario(comentario), [comentario]);

  if (!d) return <p className={s.vacio}>Cargando…</p>;

  const decision = decisionDe(d, elegida);
  async function enviar(e: FormEvent) {
    e.preventDefault();
    setIntento(true);
    if (!d || !elegida || errComentario) return;
    setEnviando(true);
    try {
      const r = await apiRevision.revisarRespuesta(d.id, elegida, comentario.trim());
      const verbo = r.decision === "confirmada" ? "Confirmaste" : "Corregiste a";
      onResuelta(`${verbo} «${NOMBRE_CLASIFICACION[elegida]}» en ${d.control.codigo ?? "la pregunta"}.` +
        (r.puntajes_recalculados ? " Los puntajes de la evaluación se recalcularon." : ""));
    } catch (err) {
      onError(err);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <div className={s.detalleCabeza}>
        <button type="button" className={`btn btn-ghost btn-sm ${s.volver}`} onClick={volver}>Volver a la lista</button>
        <div className={s.detalleMeta}>
          <span className={s.codigo}>{d.control.codigo ?? `Control ${d.control.id}`}</span>
          {d.control.dominio ? <span>{d.control.dominio}</span> : null}
          {d.control.criticidad ? <span>Criticidad {d.control.criticidad}</span> : null}
          <span>Evaluación {d.evaluacion.id}{d.evaluacion.empresa ? ` · ${d.evaluacion.empresa}` : ""}
            {d.evaluacion.cerrada ? " · cerrada" : " · en curso"}{d.evaluacion.es_prueba ? " · de prueba" : ""}</span>
        </div>
        <h2 ref={titulo} tabIndex={-1} className={s.detalleTitulo}>{d.control.pregunta ?? "Pregunta sin texto"}</h2>
        <div className={s.filaMotivos}>
          {d.motivos.map((mo: Motivo) => (
            <span key={mo} className={`badge tone-${TONO_MOTIVO[mo]}`} title={TEXTO_MOTIVO[mo].ayuda}>{TEXTO_MOTIVO[mo].corto}</span>
          ))}
        </div>
      </div>

      <div className={s.detalleCuerpo}>
        <CadenaDecision r={d} umbral={umbral} />

        <form className={s.decision} onSubmit={enviar} noValidate aria-labelledby={`${idComentario}-t`}>
          <h3 id={`${idComentario}-t`} className={s.seccionTitulo}>Tu decisión</h3>
          <fieldset className={s.opciones}>
            <legend>Clasificación final</legend>
            {RESOLUTIVAS.map((op) => (
              <label key={op} className={s.opcion}>
                <input type="radio" name={`clasif-${d.id}`} value={op} checked={elegida === op} onChange={() => setElegida(op)} />
                <span className={s.etiquetaOpcion}>
                  <span><span className={`badge tone-${TONO_CLASIFICACION[op]}`}>{NOMBRE_CLASIFICACION[op]}</span></span>
                  <small>{AYUDA_OPCION[op]}</small>
                </span>
              </label>
            ))}
          </fieldset>
          <div className={s.campo}>
            <label htmlFor={idComentario}>Comentario</label>
            <textarea id={idComentario} className={s.areaComentario} value={comentario} maxLength={COMENTARIO_MAX + 200}
                      aria-describedby={idAyuda} aria-invalid={intento && Boolean(errComentario)}
                      placeholder="Qué revisaste y por qué decides esta clasificación."
                      onChange={(e) => setComentario(e.target.value)} />
            <div className={s.pieCampo} id={idAyuda}>
              <span className={intento && errComentario ? s.errorCampo : undefined}>
                {intento && errComentario ? errComentario : "Queda en el registro de la revisión. Evita nombres o datos personales: se anonimizan igual."}
              </span>
              <span aria-live="polite">{largoComentario(comentario)}/{COMENTARIO_MAX}</span>
            </div>
          </div>
          <div className={s.acciones}>
            <button type="submit" className="btn btn-primary" disabled={!elegida || enviando}>
              {enviando ? "Guardando…" : textoBotonDecision(d, elegida)}
            </button>
            {decision === "corregida" && d.evaluacion.cerrada ? (
              <span className={s.nota}>La evaluación está cerrada: al corregir se recalculan sus puntajes.</span>
            ) : null}
          </div>
        </form>

        <section className={s.seccion} aria-labelledby={`${idComentario}-c`}>
          <h3 id={`${idComentario}-c`} className={s.seccionTitulo}>Lo que dijo la organización</h3>
          <p className={s.texto}>{d.justificacion_usuario || "Sin justificación."}</p>
          {d.control.evidencia_esperada ? (
            <dl className={s.datos}>
              <dt>Evidencia esperada</dt><dd>{d.control.evidencia_esperada}</dd>
              {d.control.articulo_referencia ? <><dt>Referencia</dt><dd>{d.control.articulo_referencia}</dd></> : null}
            </dl>
          ) : null}
        </section>

        <section className={s.seccion} aria-labelledby={`${idComentario}-e`}>
          <h3 id={`${idComentario}-e`} className={s.seccionTitulo}>Evidencias y razonamiento de la IA</h3>
          {d.evidencias.length ? (
            <ul className={s.evidencias}>
              {d.evidencias.map((e) => (
                <li key={e.id} className={s.evidencia}>
                  <div className={s.evidenciaCabeza}>
                    <strong>{e.nombre_archivo}{e.eliminada ? " (archivo eliminado)" : ""}</strong>
                    <span>{e.origen === "remediacion" ? "Remediación · " : ""}{fechaCorta(e.fecha_procesada ?? e.fecha_subida)}</span>
                  </div>
                  {e.clasificacion_llm ? (
                    <span>
                      <span className={`badge tone-${TONO_CLASIFICACION[e.clasificacion_llm as Clasificacion] ?? "info"}`}>
                        IA: {nombreClasificacion(e.clasificacion_llm)}
                      </span>{" "}
                      <span className={s.nota}>confianza {porcentaje(e.confianza)}</span>
                    </span>
                  ) : null}
                  {e.justificacion_llm ? <p className={s.razonIa}>{e.justificacion_llm}</p> : null}
                  {e.errores.length ? <p className={s.nota}>{e.errores.join(" ")}</p> : null}
                </li>
              ))}
            </ul>
          ) : <p className={s.texto}>Sin evidencias.</p>}
        </section>

        {d.eventos.length ? (
          <section className={s.seccion} aria-labelledby={`${idComentario}-s`}>
            <h3 id={`${idComentario}-s`} className={s.seccionTitulo}>Eventos de seguridad</h3>
            {d.eventos.map((ev) => (
              <div key={ev.id} className={s.seccion}>
                <span className={s.nota}>{NOMBRE_ORIGEN_EVENTO[ev.origen] ?? ev.origen} · {fechaCorta(ev.fecha)}
                  {ev.revision?.resolucion ? ` · ${NOMBRE_RESOLUCION[ev.revision.resolucion]}` : " · sin resolver"}</span>
                <blockquote className={s.extracto}>{ev.extracto ?? "Extracto eliminado por la política de retención."}</blockquote>
                {ev.regla ? <p className={s.nota}>Regla que bloqueó: <code>{ev.regla}</code></p> : null}
              </div>
            ))}
          </section>
        ) : null}

        <section className={s.seccion} aria-labelledby={`${idComentario}-h`}>
          <h3 id={`${idComentario}-h`} className={s.seccionTitulo}>Historial de revisiones</h3>
          {d.historial.length ? (
            <ol className={s.historial}>
              {d.historial.map((h) => (
                <li key={h.audit_id} className={s.paso}>
                  <span className={s.pasoTexto}>
                    <span>
                      {h.decision === "confirmada" ? "Confirmó" : h.decision === "corregida" ? "Corrigió" : "Revisó"}{" "}
                      «{nombreClasificacion(h.nueva)}»
                      {h.anterior && h.anterior !== h.nueva ? ` (antes «${nombreClasificacion(h.anterior)}»)` : ""}
                    </span>
                    <span className={s.pasoMeta}>
                      {h.revisor ?? `Administrador ${h.actor_id ?? ""}`} · {fechaCorta(h.fecha)} · registro n.º {h.audit_id} del audit log
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          ) : <p className={s.texto}>Todavía nadie la ha revisado.</p>}
          {d.revision?.comentario ? (
            <p className={s.texto}><strong>Último comentario:</strong> {d.revision.comentario}</p>
          ) : null}
        </section>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ detalle de un evento */
function PanelEvento({ evento, volver, onError, onResuelto, irARespuesta }: {
  evento: ItemEvento | null; volver: () => void; onError: (e: unknown) => void;
  onResuelto: (texto: string) => void; irARespuesta: (rid: number) => void;
}) {
  const [resolucion, setResolucion] = useState<Resolucion | null>(evento?.revision?.resolucion ?? null);
  const [comentario, setComentario] = useState("");
  const [intento, setIntento] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const idComentario = useId();
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => { titulo.current?.focus(); }, []);

  if (!evento) return <p className={s.vacio}>Este evento ya no está en la lista.</p>;
  const ev = evento;
  const errComentario = errorComentario(comentario);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setIntento(true);
    if (!resolucion || errComentario) return;
    setEnviando(true);
    try {
      await apiRevision.revisarEvento(ev.id, resolucion, comentario.trim());
      onResuelto(resolucion === "falso_positivo"
        ? "Marcaste el evento como falso positivo." + (ev.respuesta_id ? " Revisa también la clasificación de esa pregunta." : "")
        : "Confirmaste el ataque.");
    } catch (err) {
      onError(err);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <>
      <div className={s.detalleCabeza}>
        <button type="button" className={`btn btn-ghost btn-sm ${s.volver}`} onClick={volver}>Volver a la lista</button>
        <div className={s.detalleMeta}>
          <span>{NOMBRE_ORIGEN_EVENTO[ev.origen] ?? ev.origen}</span>
          <span>{fechaCorta(ev.fecha)}</span>
          {ev.evaluacion_id ? <span>Evaluación {ev.evaluacion_id}</span> : null}
          {ev.control?.codigo ? <span className={s.codigo}>{ev.control.codigo}</span> : null}
        </div>
        <h2 ref={titulo} tabIndex={-1} className={s.detalleTitulo}>Posible intento de manipular a la IA</h2>
      </div>
      <div className={s.detalleCuerpo}>
        <section className={s.seccion}>
          <p className={s.texto}>Texto detectado (ya anonimizado). No se envió a la IA.</p>
          <blockquote className={s.extracto}>{ev.extracto ?? "Extracto eliminado por la política de retención."}</blockquote>
          {ev.regla ? (
            <p className={s.texto}>
              Regla que bloqueó: <code>{ev.regla}</code>. Si el texto era legítimo, márcalo como falso positivo
              para afinar esta regla.
            </p>
          ) : null}
          {ev.control?.pregunta ? <p className={s.texto}>Pregunta: {ev.control.pregunta}</p> : null}
          {ev.respuesta_id ? (
            <p>
              <button type="button" className="link-btn" onClick={() => irARespuesta(ev.respuesta_id as number)}>
                Revisar la clasificación de esta pregunta
              </button>
            </p>
          ) : null}
        </section>

        <form className={s.decision} onSubmit={enviar} noValidate>
          <h3 className={s.seccionTitulo}>Tu veredicto</h3>
          <fieldset className={s.opciones}>
            <legend>¿Era un ataque?</legend>
            {(["ataque_confirmado", "falso_positivo"] as Resolucion[]).map((op) => (
              <label key={op} className={s.opcion}>
                <input type="radio" name={`res-${ev.id}`} checked={resolucion === op} onChange={() => setResolucion(op)} />
                <span className={s.etiquetaOpcion}>
                  <span>{NOMBRE_RESOLUCION[op]}</span>
                  <small>{op === "ataque_confirmado" ? "La detección acertó" : "El texto era legítimo"}</small>
                </span>
              </label>
            ))}
          </fieldset>
          <div className={s.campo}>
            <label htmlFor={idComentario}>Comentario</label>
            <textarea id={idComentario} className={s.areaComentario} value={comentario}
                      aria-invalid={intento && Boolean(errComentario)} aria-describedby={`${idComentario}-a`}
                      placeholder="Por qué lo consideras un ataque o un falso positivo."
                      onChange={(e) => setComentario(e.target.value)} />
            <div className={s.pieCampo} id={`${idComentario}-a`}>
              <span className={intento && errComentario ? s.errorCampo : undefined}>
                {intento && errComentario ? errComentario : "Los falsos positivos sirven para afinar las reglas de detección."}
              </span>
              <span aria-live="polite">{largoComentario(comentario)}/{COMENTARIO_MAX}</span>
            </div>
          </div>
          <div className={s.acciones}>
            <button type="submit" className="btn btn-primary" disabled={!resolucion || enviando}>
              {enviando ? "Guardando…" : resolucion ? `Guardar como «${NOMBRE_RESOLUCION[resolucion]}»` : "Elige un veredicto"}
            </button>
          </div>
        </form>

        {ev.revision ? (
          <section className={s.seccion}>
            <h3 className={s.seccionTitulo}>Revisión anterior</h3>
            <p className={s.texto}>
              {ev.revision.resolucion ? NOMBRE_RESOLUCION[ev.revision.resolucion] : "Revisado sin veredicto"} · {fechaCorta(ev.revision.fecha)}
              {ev.revision.comentario ? `\n${ev.revision.comentario}` : ""}
            </p>
          </section>
        ) : null}
      </div>
    </>
  );
}
