"use client";

/**
 * HU-32 · Bandeja de solicitudes ARCOP del panel interno (admin_therion).
 *
 * Misma estructura que la Bandeja de revisión (HU-22), para que el admin no aprenda otra
 * pantalla:
 *   - arriba, cuánto hay por atender (nuevas, en revisión, esperando al titular, en proceso
 *     y con plazo vencido); cada cifra filtra la lista;
 *   - a la izquierda, la lista con el derecho, el titular, el estado y el plazo;
 *   - a la derecha, la solicitud abierta: qué pidió el titular, una guía según el derecho, el
 *     historial y UN panel de acción que solo ofrece lo que el backend permite en ese estado,
 *     con el paso natural preseleccionado.
 * Aprobar una supresión pide una confirmación explícita (anonimiza de forma irreversible).
 * Cada acción queda en el historial de la solicitud y en el audit log (backend).
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { fechaChile } from "@/lib/fechas";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  COMENTARIO_MAX, DERECHOS, ESTADOS, ESTADOS_ARCOP, FILTROS_ADMIN_INICIALES, GUIA_ADMIN, MOTIVO_PRORROGA_MIN,
  RESPUESTA_MAX, RESPUESTA_MIN, TIPOS_ARCOP,
  accionesAdmin, apiAdminArcop, errorTexto, esFinal, mensajeError, siguientePasoAdmin, titularDe,
  type AccionAdmin, type CatalogoArcop, type DetalleArcop, type EstadoArcop, type FiltrosAdmin, type PaginaArcop, type TipoArcop,
} from "@/lib/arcop";
import { BarraAdmin } from "@/components/admin/BarraAdmin";
import a from "@/components/admin/admin.module.css";
import r from "@/components/admin/revision.module.css";
import { Icon } from "@/components/ui/Icon";
import { BadgeEstadoArcop, CampoTexto, Historial, Plazo, Progreso } from "./Comunes";
import s from "./arcop.module.css";

type Conteos = Awaited<ReturnType<typeof apiAdminArcop.conteos>>;

const CIFRAS: { clave: keyof Conteos; etiqueta: string; filtro: Partial<FiltrosAdmin>; estilo?: "alerta" | "aviso" }[] = [
  { clave: "recibida", etiqueta: "Nuevas", filtro: { estado: "recibida", vencidas: false } },
  { clave: "en_revision", etiqueta: "En revisión", filtro: { estado: "en_revision", vencidas: false } },
  { clave: "pendiente_informacion", etiqueta: "Esperando al titular", filtro: { estado: "pendiente_informacion", vencidas: false }, estilo: "aviso" },
  { clave: "en_proceso", etiqueta: "En proceso", filtro: { estado: "en_proceso", vencidas: false } },
  { clave: "vencidas", etiqueta: "Plazo vencido", filtro: { estado: null, vencidas: true }, estilo: "alerta" },
];

export function BandejaArcop() {
  const router = useRouter();
  const [filtros, setFiltros] = useState<FiltrosAdmin>(FILTROS_ADMIN_INICIALES);
  const [pagina, setPagina] = useState<PaginaArcop | null>(null);
  const [conteos, setConteos] = useState<Conteos | null>(null);
  const [catalogo, setCatalogo] = useState<CatalogoArcop | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const manejarError = useCallback(
    (e: unknown, porDefecto?: string) => {
      if (e instanceof ErrorBff && e.status === 401) {
        router.replace("/admin/login?motivo=sesion");
        return;
      }
      setError(mensajeError(e, porDefecto));
    },
    [router],
  );

  const cargarLista = useCallback(
    async (f: FiltrosAdmin) => {
      setCargando(true);
      try {
        setPagina(await apiAdminArcop.listar(f));
      } catch (e) {
        manejarError(e, "No pudimos cargar las solicitudes.");
      } finally {
        setCargando(false);
      }
    },
    [manejarError],
  );

  const cargarConteos = useCallback(async () => {
    try {
      setConteos(await apiAdminArcop.conteos());
    } catch {
      /* la franja es secundaria: sin ella la bandeja sigue sirviendo */
    }
  }, []);

  useEffect(() => {
    void cargarLista(filtros);
  }, [cargarLista, filtros]);

  useEffect(() => {
    void cargarConteos();
    apiAdminArcop.catalogo().then(setCatalogo).catch(() => setCatalogo(null));
  }, [cargarConteos]);

  const actualizarTodo = useCallback(async () => {
    setError(null);
    await Promise.all([cargarLista(filtros), cargarConteos()]);
  }, [cargarLista, cargarConteos, filtros]);

  function cambiar(parcial: Partial<FiltrosAdmin>) {
    setAbierta(null);
    setFiltros((f) => ({ ...f, page: 1, ...parcial }));
  }

  async function alActuar(texto: string) {
    setAviso(texto);
    setError(null);
    await Promise.all([cargarLista(filtros), cargarConteos()]);
  }

  const hayFiltros = Boolean(filtros.estado || filtros.tipo || filtros.vencidas || filtros.evaluacion_id);

  return (
    <div className={`${a.pagina} ${r.raiz}`}>
      <BarraAdmin onActualizar={actualizarTodo} alVolver />

      <main id="contenido" className={a.contenido}>
        <div>
          <h1 className="page-title">Solicitudes ARCOP</h1>
          <p className="page-sub">
            Atiende los derechos de acceso, rectificación, supresión, oposición, portabilidad y bloqueo de los titulares
            (Ley 21.719). Respuesta en {catalogo?.plazo_respuesta_dias ?? 30} días corridos, prorrogable una vez; el bloqueo,
            en {catalogo?.plazo_bloqueo_dias_habiles ?? 2} días hábiles. Cada acción queda en el audit log.
          </p>
        </div>

        <div className={s.franja} role="group" aria-label="Solicitudes por atender">
          {CIFRAS.map((c) => {
            const activa = c.clave === "vencidas" ? filtros.vencidas : filtros.estado === c.clave && !filtros.vencidas;
            const valor = conteos?.[c.clave];
            return (
              <button
                key={c.clave}
                type="button"
                className={`${s.cifra} ${c.estilo === "alerta" && valor ? s.cifraAlerta : ""} ${c.estilo === "aviso" && valor ? s.cifraAviso : ""}`}
                aria-pressed={activa}
                onClick={() => cambiar(activa ? { estado: null, vencidas: false } : c.filtro)}
              >
                <span className={s.cifraValor}>{valor ?? "—"}</span>
                <span className={s.cifraEtiqueta}>{c.etiqueta}</span>
              </button>
            );
          })}
        </div>

        {aviso ? (
          <p className="callout" role="status">
            <Icon name="check" aria-hidden="true" />
            <span>
              {aviso}{" "}
              <button type="button" className="link-btn" onClick={() => setAviso(null)}>Cerrar</button>
            </span>
          </p>
        ) : null}
        {error ? (
          <div className={a.alerta} role="alert">
            <strong>{error}</strong>
            <button type="button" className="link-btn" onClick={() => setError(null)}>Cerrar</button>
          </div>
        ) : null}

        <Filtros filtros={filtros} cambiar={cambiar} hayFiltros={hayFiltros} />

        <div className={r.paneles} data-abierto={abierta ? "true" : "false"}>
          <div className={r.columnaLista}>
            {cargando && !pagina ? (
              <p className={r.vacio}>Cargando las solicitudes…</p>
            ) : !pagina?.items.length ? (
              <div className={r.vacio}>
                <strong>{hayFiltros ? "Nada coincide con estos filtros" : "No hay solicitudes ARCOP"}</strong>
                <span>{hayFiltros ? "Prueba con otro estado o tipo, o limpia los filtros." : "Cuando un titular envíe una, aparecerá aquí."}</span>
              </div>
            ) : (
              <ul className={r.lista} aria-label="Solicitudes ARCOP">
                {pagina.items.map((x) => (
                  <li key={x.id_solicitud}>
                    <button type="button" className={r.fila} aria-current={abierta === x.id_solicitud}
                            onClick={() => setAbierta(x.id_solicitud)}>
                      <span className={r.filaCabeza}>
                        <span className={`${r.codigo} ${s.mono}`}>{x.codigo_seguimiento}</span>
                        <span>{fechaChile(x.fecha_creacion)}</span>
                      </span>
                      <span className={r.filaPregunta}>
                        {DERECHOS[x.tipo].nombre} · {DERECHOS[x.tipo].accion}
                      </span>
                      <span className={r.filaMotivos}>
                        <BadgeEstadoArcop estado={x.estado} />
                        <Plazo solicitud={x} />
                      </span>
                      <span className={r.filaCabeza}>{titularDe(x)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {pagina && pagina.pages > 1 ? (
              <nav className={r.paginacion} aria-label="Páginas de solicitudes">
                <button type="button" className="btn btn-ghost btn-sm" disabled={filtros.page <= 1}
                        onClick={() => setFiltros((f) => ({ ...f, page: f.page - 1 }))}>Anterior</button>
                <span>Página {pagina.page} de {pagina.pages} · {pagina.total} en total</span>
                <button type="button" className="btn btn-ghost btn-sm" disabled={filtros.page >= pagina.pages}
                        onClick={() => setFiltros((f) => ({ ...f, page: f.page + 1 }))}>Siguiente</button>
              </nav>
            ) : null}
          </div>

          <section className={r.detalle} aria-label="Solicitud abierta">
            {abierta ? (
              <DetalleAdmin key={abierta} id={abierta} catalogo={catalogo} volver={() => setAbierta(null)}
                            onActuar={alActuar} onError={manejarError} />
            ) : (
              <div className={r.vacio}>
                <strong>Elige una solicitud de la lista</strong>
                <span>Verás qué pidió el titular, su historial y las acciones disponibles.</span>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ filtros */
function Filtros({ filtros, cambiar, hayFiltros }: {
  filtros: FiltrosAdmin; cambiar: (p: Partial<FiltrosAdmin>) => void; hayFiltros: boolean;
}) {
  const idEval = useId();
  const [evaluacion, setEvaluacion] = useState(filtros.evaluacion_id ? String(filtros.evaluacion_id) : "");
  useEffect(() => {
    setEvaluacion(filtros.evaluacion_id ? String(filtros.evaluacion_id) : "");
  }, [filtros.evaluacion_id]);

  const aplicarEvaluacion = () => {
    const n = Number(evaluacion);
    const nuevo = Number.isInteger(n) && n > 0 ? n : null;
    if (nuevo !== filtros.evaluacion_id) cambiar({ evaluacion_id: nuevo });
  };

  return (
    <div className={r.filtros}>
      <div className={r.filaFiltros}>
        <label className={r.campoFiltro}>
          <span>Estado</span>
          <select className={r.selector} value={filtros.estado ?? ""}
                  onChange={(e) => cambiar({ estado: (e.target.value || null) as EstadoArcop | null })}>
            <option value="">Todos</option>
            {ESTADOS_ARCOP.map((x) => <option key={x} value={x}>{ESTADOS[x].etiqueta}</option>)}
          </select>
        </label>
        <label className={r.campoFiltro}>
          <span>Derecho</span>
          <select className={r.selector} value={filtros.tipo ?? ""}
                  onChange={(e) => cambiar({ tipo: (e.target.value || null) as TipoArcop | null })}>
            <option value="">Todos</option>
            {TIPOS_ARCOP.map((x) => <option key={x} value={x}>{DERECHOS[x].nombre}</option>)}
          </select>
        </label>
        <form className={r.campoFiltro} onSubmit={(e) => { e.preventDefault(); aplicarEvaluacion(); }}>
          <label htmlFor={idEval}><span>Evaluación n.º</span></label>
          <input id={idEval} className={`${r.selector} ${r.numero}`} inputMode="numeric" pattern="[0-9]*"
                 value={evaluacion} placeholder="Todas"
                 onChange={(e) => setEvaluacion(e.target.value.replace(/\D/g, "").slice(0, 9))}
                 onBlur={aplicarEvaluacion} />
        </form>
        <label className="check">
          <input type="checkbox" checked={filtros.vencidas} onChange={(e) => cambiar({ vencidas: e.target.checked })} />
          Solo con plazo vencido
        </label>
        {hayFiltros ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => cambiar({ ...FILTROS_ADMIN_INICIALES })}>
            Limpiar filtros
          </button>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ detalle */
const TEXTO_ACCION: Record<AccionAdmin, { opcion: string; ayuda: string; boton: string }> = {
  en_revision: { opcion: "Pasar a revisión", ayuda: "Empiezas a revisarla.", boton: "Pasar a revisión" },
  pendiente_informacion: {
    opcion: "Pedir información al titular", ayuda: "Falta un antecedente para continuar.", boton: "Pedir información",
  },
  en_proceso: { opcion: "Pasar a proceso", ayuda: "La solicitud procede y la estás aplicando.", boton: "Pasar a proceso" },
  resolver: { opcion: "Resolver", ayuda: "Se atendió lo solicitado.", boton: "Resolver solicitud" },
  rechazar: { opcion: "Rechazar", ayuda: "No procede: explica el motivo.", boton: "Rechazar solicitud" },
  prorrogar: { opcion: "Prorrogar el plazo", ayuda: "Una sola vez, antes de que venza.", boton: "Prorrogar plazo" },
};

function DetalleAdmin({ id, catalogo, volver, onActuar, onError }: {
  id: number;
  catalogo: CatalogoArcop | null;
  volver: () => void;
  onActuar: (texto: string) => Promise<void>;
  onError: (e: unknown, porDefecto?: string) => void;
}) {
  const [d, setD] = useState<DetalleArcop | null>(null);
  const [fallo, setFallo] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setD(await apiAdminArcop.detalle(id));
      setFallo(false);
    } catch (e) {
      setFallo(true);
      onError(e, "No pudimos abrir la solicitud.");
    }
  }, [id, onError]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  if (fallo) {
    return (
      <div className={r.vacio}>
        <strong>No pudimos abrir la solicitud</strong>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void cargar()}>Reintentar</button>
      </div>
    );
  }
  if (!d) return <p className={r.vacio}>Cargando la solicitud…</p>;

  const derecho = DERECHOS[d.tipo];
  const final = esFinal(d.estado);

  return (
    <>
      <div className={r.detalleCabeza}>
        <button type="button" className={`btn btn-ghost btn-sm ${r.volver}`} onClick={volver}>
          <Icon name="flecha" style={{ transform: "rotate(180deg)" }} />
          Volver a la lista
        </button>
        <h2 className={r.detalleTitulo}>{derecho.nombre} · {derecho.accion}</h2>
        <div className={r.detalleMeta}>
          <span className={s.mono}>{d.codigo_seguimiento}</span>
          <span>{titularDe(d)}</span>
          <span>Recibida el {fechaChile(d.fecha_creacion)}</span>
          <BadgeEstadoArcop estado={d.estado} />
        </div>
      </div>

      <div className={r.detalleCuerpo}>
        <div className={r.seccion}>
          <Progreso estado={d.estado} />
          <p className={s.estadoFrase}>{ESTADOS[d.estado].admin}</p>
          <Plazo solicitud={d} />
        </div>

        {!final ? (
          <p className={`${s.guia} ${d.tipo === "supresion" ? s.guiaAlerta : ""}`}>
            <Icon name={d.tipo === "supresion" ? "alerta" : "info"} aria-hidden="true" />
            <span>{GUIA_ADMIN[d.tipo]}</span>
          </p>
        ) : null}

        <div className={r.seccion}>
          <h3 className={r.seccionTitulo}>Lo que pidió el titular</h3>
          <blockquote className={s.cita}>{d.descripcion}</blockquote>
        </div>

        {d.respuesta ? (
          <div className={r.seccion}>
            <h3 className={r.seccionTitulo}>Respuesta registrada</h3>
            <blockquote className={`${s.cita} ${s.citaRespuesta}`}>{d.respuesta}</blockquote>
          </div>
        ) : null}

        {!final ? (
          <PanelAccion key={`${d.estado}-${d.fecha_prorroga ?? ""}`} d={d} catalogo={catalogo} onListo={async (nuevo, texto) => { setD(nuevo); await onActuar(texto); }}
                       onConflicto={cargar} onError={onError} />
        ) : null}

        <div className={r.seccion}>
          <h3 className={r.seccionTitulo}>Historial</h3>
          <Historial eventos={d.historial} paraTitular={false} />
        </div>
      </div>
    </>
  );
}

function PanelAccion({ d, catalogo, onListo, onConflicto, onError }: {
  d: DetalleArcop;
  catalogo: CatalogoArcop | null;
  onListo: (nuevo: DetalleArcop, texto: string) => Promise<void>;
  onConflicto: () => Promise<void>;
  onError: (e: unknown, porDefecto?: string) => void;
}) {
  const disponibles = accionesAdmin(d);
  const sugerida = siguientePasoAdmin(d);
  const [accion, setAccion] = useState<AccionAdmin | null>(
    sugerida && disponibles.includes(sugerida) ? sugerida : disponibles[0] ?? null,
  );
  const [texto, setTexto] = useState("");
  const [confirmado, setConfirmado] = useState(false);
  const [intentado, setIntentado] = useState(false);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    setTexto("");
    setIntentado(false);
    setConfirmado(false);
  }, [accion]);

  if (!accion) return null;

  const esSupresion = d.tipo === "supresion" && accion === "resolver";
  const requiereRespuesta = accion === "resolver" || accion === "rechazar";
  const requiereComentario = accion === "pendiente_informacion";
  const esProrroga = accion === "prorrogar";

  const errorCampo = !intentado
    ? null
    : requiereRespuesta
      ? errorTexto(texto, RESPUESTA_MIN, RESPUESTA_MAX, "La respuesta")
      : esProrroga
        ? errorTexto(texto, MOTIVO_PRORROGA_MIN, COMENTARIO_MAX, "El motivo")
        : requiereComentario
          ? errorTexto(texto, 1, COMENTARIO_MAX, "Lo que necesitas")
          : null;

  async function ejecutar(e: FormEvent) {
    e.preventDefault();
    setIntentado(true);
    if (!accion || enviando) return;
    const invalido = requiereRespuesta
      ? errorTexto(texto, RESPUESTA_MIN, RESPUESTA_MAX)
      : esProrroga
        ? errorTexto(texto, MOTIVO_PRORROGA_MIN, COMENTARIO_MAX)
        : requiereComentario
          ? errorTexto(texto, 1, COMENTARIO_MAX)
          : null;
    if (invalido || (esSupresion && !confirmado)) return;

    setEnviando(true);
    try {
      let nuevo: DetalleArcop;
      let aviso: string;
      switch (accion) {
        case "resolver":
          nuevo = await apiAdminArcop.resolver(d.id_solicitud, "resuelta", texto);
          aviso = d.tipo === "supresion"
            ? `${d.codigo_seguimiento} resuelta: los datos del titular quedaron anonimizados.`
            : `${d.codigo_seguimiento} resuelta.${d.tipo === "acceso" || d.tipo === "portabilidad" ? " El titular ya puede descargar sus datos." : ""}`;
          break;
        case "rechazar":
          nuevo = await apiAdminArcop.resolver(d.id_solicitud, "rechazada", texto);
          aviso = `${d.codigo_seguimiento} rechazada.`;
          break;
        case "prorrogar":
          nuevo = await apiAdminArcop.prorrogar(d.id_solicitud, texto);
          aviso = `Plazo de ${d.codigo_seguimiento} prorrogado ${catalogo?.plazo_prorroga_dias ?? 30} días.`;
          break;
        default:
          nuevo = await apiAdminArcop.cambiarEstado(d.id_solicitud, accion, texto);
          aviso = `${d.codigo_seguimiento} pasó a «${ESTADOS[accion].etiqueta}».`;
      }
      await onListo(nuevo, aviso);
    } catch (err) {
      onError(err);
      if (err instanceof ErrorBff && err.status === 409) await onConflicto();
    } finally {
      setEnviando(false);
    }
  }

  const etiquetaTexto = requiereRespuesta
    ? accion === "rechazar" ? "Motivo del rechazo (lo verá el titular)" : "Respuesta al titular"
    : esProrroga
      ? "Motivo de la prórroga (lo verá el titular)"
      : requiereComentario
        ? "¿Qué antecedente necesitas del titular?"
        : "Comentario para el historial";

  const ayudaTexto = requiereRespuesta
    ? "No incluyas datos personales del titular: la respuesta se conserva aunque se anonimicen sus datos."
    : esProrroga
      ? `Se suman ${catalogo?.plazo_prorroga_dias ?? 30} días al plazo. La ley permite prorrogar una sola vez.`
      : requiereComentario
        ? "Sé específico: el titular lo verá y podrá responder desde su página."
        : "El titular verá este comentario en el historial de su solicitud.";

  return (
    <form className={r.decision} onSubmit={ejecutar} noValidate aria-labelledby={`titulo-accion-${d.id_solicitud}`}>
      <h3 id={`titulo-accion-${d.id_solicitud}`} className={r.seccionTitulo}>¿Qué quieres hacer?</h3>
      <fieldset className={r.opciones}>
        <legend className="sr-only">Acción sobre la solicitud</legend>
        {disponibles.map((x) => (
          <label key={x} className={r.opcion}>
            <input type="radio" name={`accion-${d.id_solicitud}`} value={x} checked={accion === x} onChange={() => setAccion(x)} />
            <span className={r.etiquetaOpcion}>
              {TEXTO_ACCION[x].opcion}
              {x === sugerida ? " (siguiente paso)" : ""}
              <small>{TEXTO_ACCION[x].ayuda}</small>
            </span>
          </label>
        ))}
      </fieldset>

      <CampoTexto
        key={accion}
        etiqueta={etiquetaTexto}
        ayuda={ayudaTexto}
        valor={texto}
        onCambio={setTexto}
        max={requiereRespuesta ? RESPUESTA_MAX : COMENTARIO_MAX}
        error={errorCampo}
        obligatorio={requiereRespuesta || esProrroga || requiereComentario}
        corto={!requiereRespuesta}
      />

      {esSupresion ? (
        <label className={s.confirmar}>
          <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)} />
          <span>
            <strong>Confirmo la supresión.</strong> Se anonimizarán de forma irreversible los datos personales del titular
            (correo, nombre, justificaciones, evidencias y sus archivos) y perderá su acceso. Se conservan los puntajes sin
            vínculo personal.
          </span>
        </label>
      ) : null}
      {esSupresion && intentado && !confirmado ? (
        <p className={s.error} role="alert">Marca la casilla para confirmar la supresión.</p>
      ) : null}

      <div className={r.acciones}>
        <button
          type="submit"
          className={`btn ${esSupresion || accion === "rechazar" ? s.btnPeligro : "btn-primary"}`}
          disabled={enviando}
          aria-busy={enviando}
        >
          {enviando ? "Guardando…" : esSupresion ? "Aprobar supresión y anonimizar" : TEXTO_ACCION[accion].boton}
        </button>
      </div>
    </form>
  );
}
