"use client";

/**
 * Asistente de registro, dentro del mapa de datos y del registro de actividades (como el tutor IA).
 *
 *   [✦ Asistente]  botón flotante en la esquina de las dos vistas
 *
 *   ┌ Asistente de registro ───────────────────────────── [nueva] [×] ┐
 *   │ [ Preguntar ]  [ Revisar mi registro · 3 ]                       │
 *   ├──────────────────────────────────────────────────────────────────┤
 *   │ Preguntar: respuestas cortas que orientan (no arma registros),   │
 *   │            con preguntas sugeridas para seguir.                  │
 *   │ Revisar:   el paso que conviene hacer ahora y una tarjeta por    │
 *   │            tipo de problema, con qué hacer y un botón para ir.   │
 *   ├──────────────────────────────────────────────────────────────────┤
 *   │ [ Escribe tu pregunta…                              ] [Enviar]   │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 * La conversación se guarda en el navegador (sessionStorage) y se comparte entre las dos vistas.
 * `?asistente=1` en la URL lo abre al cargar. Todo el texto se pinta como texto con React (nunca HTML).
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Icon } from "@/components/ui/Icon";
import s from "@/components/formacion/tutor.module.css";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  agruparRevision, cantidad, cargarResumenGuia, cuotaTexto, guardarConversacion, leerConversacion, mensajeGuia,
  MAX_CARACTERES_GUIA, nuevoId, parrafos, pasoSiguiente, preguntaAlerta, preguntarGuia, validarPregunta,
  type AlertaRegistro, type CuotaGuia, type GrupoRevision, type MensajeGuia, type ResumenGuia, type VistaGuia,
} from "@/lib/guiaRegistro";
import g from "./guia.module.css";

const RUTA: Record<VistaGuia, string> = { mapa: "/empresa/mapa-datos", registro: "/empresa/registro-actividades" };

export interface AccionesGuia {
  /** Abre una actividad del registro (solo en la vista del registro). */
  abrirActividad?: (id: number) => void;
  /** Abre un flujo del mapa (solo en la vista del mapa). */
  abrirFlujo?: (id: number) => void;
}

export function GuiaRegistro({ vista, acciones = {} }: { vista: VistaGuia; acciones?: AccionesGuia }) {
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("asistente") === "1") setAbierto(true);
  }, []);

  return (
    <>
      <button type="button" className={`btn btn-primary ${g.lanzador}`} onClick={() => setAbierto(true)}
        aria-haspopup="dialog" aria-expanded={abierto}>
        <Icon name="chispa" />
        Asistente
      </button>
      {abierto ? <Panel vista={vista} acciones={acciones} onCerrar={() => setAbierto(false)} /> : null}
    </>
  );
}

type Pestana = "preguntar" | "revisar";

function Panel({ vista, acciones, onCerrar }: { vista: VistaGuia; acciones: AccionesGuia; onCerrar: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const router = useRouter();
  const idTitulo = useId();
  const [pestana, setPestana] = useState<Pestana>("preguntar");
  const [resumen, setResumen] = useState<ResumenGuia | null>(null);
  const [errorCarga, setErrorCarga] = useState("");
  const [mensajes, setMensajes] = useState<MensajeGuia[]>([]);
  const [cuota, setCuota] = useState<CuotaGuia | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");

  const cargar = useCallback(async () => {
    setErrorCarga("");
    try {
      const r = await cargarResumenGuia();
      setResumen(r);
      setCuota(r.ia.cuota);
    } catch (e) {
      if (e instanceof ErrorBff && e.status === 401) {
        router.replace("/ingresar?motivo=sesion");
        return;
      }
      setErrorCarga(mensajeGuia(e));
    }
  }, [router]);

  // La página de atrás no hace scroll mientras el panel está abierto (igual que el tutor)
  useEffect(() => {
    const html = document.documentElement;
    const antes = html.style.overflow;
    html.style.overflow = "hidden";
    return () => {
      html.style.overflow = antes;
    };
  }, []);

  useEffect(() => {
    if (ref.current && !ref.current.open) ref.current.showModal();
    setMensajes(leerConversacion(typeof window === "undefined" ? null : window.sessionStorage));
    void cargar();
  }, [cargar]);

  useEffect(() => {
    guardarConversacion(typeof window === "undefined" ? null : window.sessionStorage, mensajes);
  }, [mensajes]);

  const cerrar = () => ref.current?.close();

  /** Devuelve true si se envió (el composer se limpia). */
  const enviar = async (texto: string): Promise<boolean> => {
    if (enviando) return false;
    const v = validarPregunta(texto, resumen?.limites.max_caracteres ?? MAX_CARACTERES_GUIA);
    if (!v.ok) {
      setError(v.motivo);
      return false;
    }
    setPestana("preguntar");
    setError("");
    setEnviando(true);
    const anteriores = mensajes;
    const propio: MensajeGuia = { id: nuevoId(), rol: "usuario", texto: v.texto };
    setMensajes([...anteriores, propio]);
    try {
      const r = await preguntarGuia(v.texto, vista, anteriores);
      setCuota(r.cuota);
      setMensajes((m) => [
        ...m.map((x) => (x.id === propio.id && r.bloqueado ? { ...x, bloqueado: true } : x)),
        { id: nuevoId(), rol: "guia", texto: r.respuesta, sugerencias: r.sugerencias },
      ]);
      return true;
    } catch (e) {
      if (e instanceof ErrorBff && e.status === 401) {
        router.replace("/ingresar?motivo=sesion");
        return false;
      }
      setMensajes((m) => m.filter((x) => x.id !== propio.id));
      setError(mensajeGuia(e));
      return false;
    } finally {
      setEnviando(false);
    }
  };

  /** Lleva a resolver una alerta: en la misma vista abre la ficha; si es de la otra vista, navega. */
  const irA = (a: AlertaRegistro | null, destino: VistaGuia) => {
    const id = a?.referencia?.id;
    if (a?.referencia?.tipo === "actividad" && id && acciones.abrirActividad) acciones.abrirActividad(id);
    else if (a?.referencia?.tipo === "flujo" && id && acciones.abrirFlujo) acciones.abrirFlujo(id);
    else if (a?.referencia?.tipo === "actividad" && id) router.push(`${RUTA.registro}?actividad=${id}`);
    else if (destino !== vista) router.push(RUTA[destino]);
    cerrar();
  };

  const pendientes = resumen?.revision.length ?? 0;

  return (
    <dialog ref={ref} className={s.panel} aria-labelledby={idTitulo} onClose={onCerrar}>
      <div className={s.marco}>
        <header className={s.cabeza}>
          <div className={s.titulos}>
            <h2 className={s.titulo} id={idTitulo}>
              <Icon name="chispa" />
              Asistente de registro
            </h2>
            <p className={s.subtitulo}>Te oriento paso a paso. Tú completas y decides qué se guarda.</p>
          </div>
          <div className={s.acciones}>
            <button type="button" className="icon-btn" onClick={() => { setMensajes([]); setError(""); }}
              aria-label="Nueva conversación" title="Nueva conversación" disabled={enviando || !mensajes.length}>
              <Icon name="mas" />
            </button>
            <button type="button" className="icon-btn" onClick={cerrar} aria-label="Cerrar el asistente">
              <Icon name="cerrar" />
            </button>
          </div>
        </header>

        <div className={g.pestanas} role="tablist" aria-label="Qué quieres hacer">
          <button type="button" role="tab" aria-selected={pestana === "preguntar"} onClick={() => setPestana("preguntar")}>
            <Icon name="mensaje" /> Preguntar
          </button>
          <button type="button" role="tab" aria-selected={pestana === "revisar"} onClick={() => setPestana("revisar")}>
            <Icon name="check" /> Revisar mi registro
            {pendientes ? <span className={g.contador} aria-label={`${pendientes} por resolver`}>{pendientes}</span> : null}
          </button>
        </div>

        {pestana === "revisar" ? (
          <Revision resumen={resumen} error={errorCarga} onReintentar={cargar} onIr={irA}
            onPreguntar={(grupo) => void enviar(preguntaAlerta(grupo))} enviando={enviando} />
        ) : (
          <Chat vista={vista} resumen={resumen} mensajes={mensajes} enviando={enviando} error={error} cuota={cuota}
            onEnviar={enviar} onLimpiarError={() => setError("")} />
        )}
      </div>
    </dialog>
  );
}

/* ================================================================== preguntar */
function Chat({
  vista, resumen, mensajes, enviando, error, cuota, onEnviar, onLimpiarError,
}: {
  vista: VistaGuia;
  resumen: ResumenGuia | null;
  mensajes: MensajeGuia[];
  enviando: boolean;
  error: string;
  cuota: CuotaGuia | null;
  onEnviar: (t: string) => Promise<boolean>;
  onLimpiarError: () => void;
}) {
  const [texto, setTexto] = useState("");
  const log = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);
  const idAyuda = useId();
  const max = resumen?.limites.max_caracteres ?? MAX_CARACTERES_GUIA;
  const sinCuota = cuota?.restantes === 0 && resumen?.ia.habilitada !== false;
  const ultima = [...mensajes].reverse().find((m) => m.rol === "guia");

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [mensajes.length, enviando]);

  useEffect(() => {
    entrada.current?.focus();
  }, []);

  const mandar = async (contenido: string) => {
    onLimpiarError();
    const anterior = texto;
    setTexto("");
    if (!(await onEnviar(contenido))) setTexto(anterior || contenido); // la pregunta no se pierde si falla
  };

  const alEnviar = (e: FormEvent) => {
    e.preventDefault();
    void mandar(texto);
  };
  const alTeclear = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void mandar(texto);
    }
  };

  const iniciales = resumen?.sugerencias[vista] ?? [];

  return (
    <>
      <div className={s.log} ref={log} role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversación con el asistente">
        {mensajes.length === 0 ? (
          <div className={s.bienvenida}>
            <p className={s.bienvenidaTitulo}>¿En qué te ayudo?</p>
            <p className={s.bienvenidaTexto}>
              Pregúntame qué significa algo o qué hacer ahora en tu {vista === "mapa" ? "mapa de datos" : "registro de actividades"}.
              Te respondo corto y te digo dónde hacerlo. No compartas datos de personas.
            </p>
            {iniciales.length ? (
              <ul className={s.sugerencias} aria-label="Preguntas sugeridas">
                {iniciales.map((q) => (
                  <li key={q}>
                    <button type="button" className="chip" onClick={() => void mandar(q)} disabled={enviando || sinCuota}>{q}</button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : (
          mensajes.map((m) =>
            m.rol === "usuario" ? (
              <div key={m.id} className={`${s.mensaje} ${s.usuario}`} data-bloqueado={m.bloqueado || undefined}>
                <span className="sr-only">Tú dijiste: </span>
                {parrafos(m.texto).map((p, i) => <p key={i}>{p}</p>)}
              </div>
            ) : (
              <article key={m.id} className={`${s.mensaje} ${s.tutor}`} aria-label="Respuesta del asistente">
                {parrafos(m.texto).map((p, i) => <p key={i}>{p}</p>)}
                {m === ultima && m.sugerencias?.length && !enviando && !sinCuota ? (
                  <ul className={s.sugerencias} aria-label="Siguientes preguntas sugeridas">
                    {m.sugerencias.map((q) => (
                      <li key={q}><button type="button" className="chip" onClick={() => void mandar(q)}>{q}</button></li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ),
          )
        )}
        {enviando ? (
          <div className={`${s.mensaje} ${s.tutor}`} role="status">
            <span className={s.puntos} aria-hidden="true"><i /><i /><i /></span>
            <span className="sr-only">El asistente está escribiendo…</span>
          </div>
        ) : null}
      </div>

      <form className={s.composer} onSubmit={alEnviar} noValidate>
        {error ? (
          <p className={s.error} role="alert"><Icon name="alerta" />{error}</p>
        ) : null}
        <div className={s.entrada}>
          <label htmlFor={`${idAyuda}-texto`} className="sr-only">Tu pregunta para el asistente</label>
          <textarea id={`${idAyuda}-texto`} ref={entrada} className={s.textarea} rows={2} maxLength={max}
            placeholder={sinCuota ? "Usaste las preguntas de hoy" : "Escribe tu pregunta… (Enter envía)"}
            value={texto} onChange={(e) => setTexto(e.target.value)} onKeyDown={alTeclear} disabled={sinCuota}
            aria-describedby={idAyuda} />
          <button type="submit" className={`btn btn-primary ${s.enviar}`} disabled={enviando || sinCuota || !texto.trim()}
            aria-busy={enviando}>
            <Icon name="enviar" />
            <span className="sr-only">Enviar</span>
          </button>
        </div>
        <p className={s.pie} id={idAyuda}>
          <span>{cuotaTexto(cuota, resumen?.ia.habilitada ?? true)}</span>
          <span>{texto.length > max * 0.8 ? `${texto.length}/${max}` : ""}</span>
        </p>
        <p className={s.legal}>Orientación general; no reemplaza la asesoría legal.</p>
      </form>
    </>
  );
}

/* ================================================================== revisar mi registro */
function Revision({
  resumen, error, onReintentar, onIr, onPreguntar, enviando,
}: {
  resumen: ResumenGuia | null;
  error: string;
  onReintentar: () => void;
  onIr: (a: AlertaRegistro | null, vista: VistaGuia) => void;
  onPreguntar: (g: GrupoRevision) => void;
  enviando: boolean;
}) {
  if (error) {
    return (
      <div className={s.centro} role="alert">
        <Icon name="alerta" width={28} height={28} />
        <p>{error}</p>
        <button type="button" className="btn btn-primary btn-sm" onClick={onReintentar}>
          <Icon name="refrescar" /> Reintentar
        </button>
      </div>
    );
  }
  if (!resumen) {
    return (
      <div className={s.centro} role="status">
        <span className={s.puntos} aria-hidden="true"><i /><i /><i /></span>
        Revisando tu registro…
      </div>
    );
  }
  const paso = pasoSiguiente(resumen);
  const grupos = agruparRevision(resumen.revision);
  const m = resumen.mapa;

  return (
    <div className={g.revision}>
      <p className={g.resumen}>
        Tienes {cantidad(m.elementos, "elemento", "elementos")} en el mapa, {cantidad(m.flujos, "flujo", "flujos")} y{" "}
        {cantidad(m.actividades, "actividad", "actividades")} en el registro.
      </p>

      <section className={`${g.paso} ${paso.id === "listo" ? g.pasoListo : ""}`} aria-label="Lo que conviene hacer ahora">
        <Icon name={paso.id === "listo" ? "check" : "diana"} />
        <div>
          <p className={g.pasoEtiqueta}>{paso.id === "listo" ? "Todo en orden" : "Ahora te conviene"}</p>
          <p className={g.pasoTitulo}>{paso.titulo}</p>
          <p className={g.pasoTexto}>{paso.texto}</p>
          {paso.id !== "listo" && paso.id !== "alertas" ? (
            <button type="button" className="btn btn-primary btn-sm" onClick={() => onIr(null, paso.vista)}>
              {paso.vista === "mapa" ? "Ir al mapa de datos" : "Ir al registro"}
            </button>
          ) : null}
        </div>
      </section>

      {grupos.length ? (
        <ul className={g.grupos} aria-label="Puntos por resolver">
          {grupos.map((grupo) => (
            <li key={grupo.codigo} className={g.grupo} data-severidad={grupo.severidad}>
              <p className={g.grupoTitulo}>
                <span>{grupo.titulo}</span>
                <span className={g.grupoCantidad}>{grupo.items.length}</span>
              </p>
              <p className={g.queHacer}>{grupo.queHacer}</p>
              <details className={g.detalle}>
                <summary>Ver {grupo.items.length === 1 ? "cuál es" : "cuáles son"}</summary>
                <ul>
                  {grupo.items.slice(0, 8).map((a, i) => (
                    <li key={i}>
                      <span>{a.texto}</span>
                      <button type="button" className={g.enlace} onClick={() => onIr(a, grupo.vista)}>
                        Resolver<span className="sr-only">: {a.texto}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
              <div className={g.grupoAcciones}>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => onIr(grupo.items[0] ?? null, grupo.vista)}>
                  Resolver ahora
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => onPreguntar(grupo)} disabled={enviando}>
                  <Icon name="mensaje" /> ¿Cómo lo resuelvo?
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
