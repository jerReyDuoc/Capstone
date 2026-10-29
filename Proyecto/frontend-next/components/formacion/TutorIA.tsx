"use client";

/**
 * HU-15 · Agente IA Tutor en el panel de formación (solo el usuario definitivo).
 *
 *   ┌ Tutor IA ───────────────────────── [historial] [nueva] [×] ┐
 *   │ Basado en tus 12 brechas · Evaluación N.º 34                │
 *   │ Nivel  (Inicial) (Intermedio) (Avanzado)                    │
 *   ├─────────────────────────────────────────────────────────────┤
 *   │ conversación (role=log): explicaciones, planes de acción    │
 *   │ con pasos y evidencia esperada, brechas citadas → enlaces   │
 *   │ al listado y a "Subir evidencia" (HU-17)                    │
 *   ├─────────────────────────────────────────────────────────────┤
 *   │ [ Escribe tu pregunta…                        ] [Enviar]    │
 *   │ Te quedan 57 de 60 mensajes hoy · no es asesoría legal      │
 *   └─────────────────────────────────────────────────────────────┘
 *
 * Se abre como panel lateral (<dialog> modal: foco atrapado y Esc para cerrar; pantalla
 * completa en móvil). La respuesta es síncrona: mientras el tutor escribe se muestra un
 * indicador anunciado a lectores de pantalla.
 */
import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { BadgeSeveridad } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";
import { usePanel } from "@/hooks/usePanel";
import { useTutor } from "@/hooks/useTutor";
import { fechaLarga, hrefModulo, hrefRemediacion } from "@/lib/formacion";
import {
  cuotaTexto,
  horaCorta,
  MAX_CARACTERES_TUTOR,
  NIVEL_TUTOR_INFO,
  NIVELES_TUTOR,
  parrafos,
  preguntaPaso,
  sugerenciasIniciales,
  TIPO_RESPUESTA,
  validarMensaje,
} from "@/lib/tutor";
import type { MensajeTutorApi } from "@/lib/types";
import s from "./tutor.module.css";

type Variante = "tarjeta" | "boton";

/** Punto de entrada: tarjeta en Capacitación o botón en un módulo. Solo para el modo "cliente". */
export function TutorIA({ rutaId = null, nombreModulo, variante = "tarjeta" }: {
  rutaId?: number | null;
  nombreModulo?: string;
  variante?: Variante;
}) {
  const { modo } = usePanel();
  const [abierto, setAbierto] = useState(false);
  if (modo !== "cliente") return null;

  const abrir = () => setAbierto(true);
  return (
    <>
      {variante === "tarjeta" ? (
        <section className={`card ${s.tarjeta}`} aria-labelledby="tutor-cta-titulo">
          <span className={s.tarjetaIcono} aria-hidden="true">
            <Icon name="chispa" />
          </span>
          <div className={s.tarjetaTexto}>
            <h2 className="card-title" id="tutor-cta-titulo">Tutor IA de gobernanza</h2>
            <p className="card-sub">
              Pregunta por cualquiera de tus brechas: te explica la obligación, arma un plan de acción paso a paso y te dice
              qué evidencia subir para mejorar el control. Se adapta a tu nivel.
            </p>
          </div>
          <button type="button" className="btn btn-primary" onClick={abrir} aria-haspopup="dialog">
            <Icon name="mensaje" />
            Hablar con el tutor
          </button>
        </section>
      ) : (
        <button type="button" className="btn btn-ghost btn-sm" onClick={abrir} aria-haspopup="dialog">
          <Icon name="chispa" />
          Preguntar al tutor IA
          {nombreModulo ? <span className="sr-only"> sobre {nombreModulo}</span> : null}
        </button>
      )}
      {abierto ? <PanelTutor rutaId={rutaId} onCerrar={() => setAbierto(false)} /> : null}
    </>
  );
}

function PanelTutor({ rutaId, onCerrar }: { rutaId: number | null; onCerrar: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const { estado, iniciar, enviar, cambiarNivel, nueva, abrir, borrar, limpiarError } = useTutor(rutaId);
  const [vista, setVista] = useState<"chat" | "historial">("chat");
  const idTitulo = useId();
  const idNivel = useId();

  // Mientras el tutor está abierto la página de atrás no hace scroll ni muestra su barra.
  // (Sin scrollbar-gutter: en Chrome achica el área del panel fijo y deja una franja vacía.)
  useEffect(() => {
    const html = document.documentElement;
    const antes = html.style.overflow;
    html.style.overflow = "hidden";
    return () => {
      html.style.overflow = antes;
    };
  }, []);

  useEffect(() => {
    // En desarrollo (StrictMode) el efecto corre dos veces: no reabrir un diálogo abierto
    if (ref.current && !ref.current.open) ref.current.showModal();
    void iniciar();
  }, [iniciar]);

  // close() dispara onClose, que avisa al padre (también al cerrar con Esc)
  const cerrar = () => ref.current?.close();

  const ctx = estado.contexto;
  const soloLectura = estado.conversacion?.estado === "solo_lectura";

  return (
    <dialog ref={ref} className={s.panel} aria-labelledby={idTitulo} onClose={onCerrar}>
      <div className={s.marco}>
        <header className={s.cabeza}>
          <div className={s.titulos}>
            <h2 className={s.titulo} id={idTitulo}>
              <Icon name="chispa" />
              Tutor IA
            </h2>
            <p className={s.subtitulo}>
              {ctx
                ? `Basado en ${ctx.brechas_total === 1 ? "tu brecha" : `tus ${ctx.brechas_total} brechas`} de la evaluación N.º ${ctx.evaluacion_id}${ctx.fecha_evaluacion ? ` (${fechaLarga(ctx.fecha_evaluacion)})` : ""}`
                : "Cargando tus brechas…"}
            </p>
          </div>
          <div className={s.acciones}>
            <button
              type="button"
              className="icon-btn"
              onClick={() => setVista((v) => (v === "chat" ? "historial" : "chat"))}
              aria-pressed={vista === "historial"}
              aria-label="Conversaciones anteriores"
              title="Conversaciones anteriores"
              disabled={estado.fase !== "listo"}
            >
              <Icon name="historial" />
            </button>
            <button
              type="button"
              className="icon-btn"
              onClick={() => {
                nueva();
                setVista("chat");
              }}
              aria-label="Nueva conversación"
              title="Nueva conversación"
              disabled={estado.fase !== "listo" || estado.enviando}
            >
              <Icon name="mas" />
            </button>
            <button type="button" className="icon-btn" onClick={cerrar} aria-label="Cerrar el tutor">
              <Icon name="cerrar" />
            </button>
          </div>
        </header>

        {estado.fase === "listo" && vista === "chat" ? (
          <div className={s.nivel} role="radiogroup" aria-labelledby={idNivel}>
            <span className={s.nivelEtiqueta} id={idNivel}>Nivel</span>
            <div className={s.segmentos}>
              {NIVELES_TUTOR.map((n) => (
                <button
                  key={n}
                  type="button"
                  role="radio"
                  aria-checked={estado.nivel === n}
                  className={s.segmento}
                  data-nivel={n}
                  onClick={() => void cambiarNivel(n)}
                  disabled={soloLectura || estado.enviando}
                >
                  {n}
                  {ctx?.nivel_sugerido === n ? <span className={s.sugerido}> · sugerido</span> : null}
                </button>
              ))}
            </div>
            <p className={s.nivelInfo}>{NIVEL_TUTOR_INFO[estado.nivel]}</p>
          </div>
        ) : null}

        {estado.fase === "cargando" || estado.fase === "inactivo" ? (
          <div className={s.centro} role="status" aria-live="polite">
            <span className={s.puntos} aria-hidden="true"><i /><i /><i /></span>
            Preparando el tutor con tus brechas…
          </div>
        ) : estado.fase === "sin-servicio" || estado.fase === "error" ? (
          <div className={s.centro} role="alert">
            <Icon name={estado.fase === "sin-servicio" ? "candado" : "alerta"} width={28} height={28} />
            <p>{estado.error}</p>
            {estado.fase === "error" ? (
              <button type="button" className="btn btn-primary btn-sm" onClick={() => void iniciar()}>
                <Icon name="refrescar" />
                Reintentar
              </button>
            ) : (
              <Link href="/ingresar" className="btn btn-primary btn-sm">Ingresar con mi empresa</Link>
            )}
          </div>
        ) : vista === "historial" ? (
          <Historial
            items={estado.conversaciones}
            actual={estado.conversacion?.id ?? null}
            onAbrir={(id) => {
              void abrir(id);
              setVista("chat");
            }}
            onBorrar={(id) => void borrar(id)}
          />
        ) : (
          <Chat
            estado={estado}
            soloLectura={soloLectura}
            onEnviar={enviar}
            onNueva={nueva}
            onLimpiarError={limpiarError}
          />
        )}
      </div>
    </dialog>
  );
}

function Chat({
  estado,
  soloLectura,
  onEnviar,
  onNueva,
  onLimpiarError,
}: {
  estado: ReturnType<typeof useTutor>["estado"];
  soloLectura: boolean;
  onEnviar: (t: string) => Promise<boolean>;
  onNueva: () => void;
  onLimpiarError: () => void;
}) {
  const [texto, setTexto] = useState("");
  const [aviso, setAviso] = useState("");
  const log = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);
  const idAyuda = useId();
  const idError = useId();
  const max = estado.contexto?.max_caracteres ?? MAX_CARACTERES_TUTOR;
  const sinCuota = estado.cuota?.restantes === 0;
  const { evaluacionId, href } = usePanel();

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [estado.mensajes.length, estado.enviando]);

  useEffect(() => {
    if (!soloLectura) entrada.current?.focus();
  }, [soloLectura, estado.conversacion?.id]);

  const mandar = async (contenido: string) => {
    const v = validarMensaje(contenido, max);
    if (!v.ok) {
      setAviso(v.motivo);
      return;
    }
    setAviso("");
    onLimpiarError();
    const anterior = texto;
    setTexto("");
    const ok = await onEnviar(v.texto);
    if (!ok) setTexto(anterior || v.texto); // el mensaje no se pierde si falla
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

  const sugerencias = sugerenciasIniciales(estado.contexto);
  const error = aviso || estado.error;

  return (
    <>
      <div className={s.log} ref={log} role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversación con el tutor">
        {estado.mensajes.length === 0 ? (
          <div className={s.bienvenida}>
            <p className={s.bienvenidaTitulo}>¿En qué brecha trabajamos hoy?</p>
            <p className={s.bienvenidaTexto}>
              Solo veo las brechas abiertas de tu evaluación vigente
              {estado.contexto?.foco ? <> y te oriento desde el módulo «{estado.contexto.foco.nombre}»</> : null}. Anonimizo
              cualquier dato personal que escribas antes de procesarlo.
            </p>
            {sugerencias.length ? (
              <ul className={s.sugerencias} aria-label="Preguntas sugeridas">
                {sugerencias.map((q) => (
                  <li key={q}>
                    <button type="button" className="chip" onClick={() => void mandar(q)} disabled={estado.enviando || sinCuota}>
                      {q}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : (
          estado.mensajes.map((m) => (
            <Mensaje
              key={m.id}
              m={m}
              hrefBrecha={(codigo) => href("/panel/brechas", { q: codigo })}
              hrefEvidencia={(respuestaId) => hrefRemediacion(evaluacionId, respuestaId)}
              hrefRuta={(rutaId) => hrefModulo(rutaId, evaluacionId)}
              onSugerencia={soloLectura || estado.enviando || sinCuota ? undefined : (q) => void mandar(q)}
            />
          ))
        )}
        {estado.enviando ? (
          <div className={`${s.mensaje} ${s.tutor}`} role="status">
            <span className={s.puntos} aria-hidden="true"><i /><i /><i /></span>
            <span className="sr-only">El tutor está escribiendo…</span>
          </div>
        ) : null}
      </div>

      {soloLectura ? (
        <div className={s.soloLectura} role="status">
          <Icon name="info" />
          <p>Esta conversación es de una evaluación anterior de tu empresa. Para usar tus brechas vigentes, abre una nueva.</p>
          <button type="button" className="btn btn-primary btn-sm" onClick={onNueva}>
            <Icon name="mas" />
            Nueva conversación
          </button>
        </div>
      ) : (
        <form className={s.composer} onSubmit={alEnviar} noValidate>
          {estado.advertencia ? (
            <p className={s.advertencia} role="alert">
              <Icon name="alerta" />
              {estado.advertencia}
            </p>
          ) : null}
          {error ? (
            <p className={s.error} id={idError} role="alert">
              <Icon name="alerta" />
              {error}
            </p>
          ) : null}
          <div className={s.entrada}>
            <label htmlFor={`${idAyuda}-texto`} className="sr-only">Tu pregunta para el tutor</label>
            <textarea
              id={`${idAyuda}-texto`}
              ref={entrada}
              className={s.textarea}
              rows={2}
              maxLength={max}
              placeholder={sinCuota ? "Usaste los mensajes de hoy" : "Escribe tu pregunta… (Enter envía, Mayús+Enter salto de línea)"}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={alTeclear}
              disabled={sinCuota}
              aria-describedby={`${idAyuda}${error ? ` ${idError}` : ""}`}
              aria-invalid={Boolean(aviso) || undefined}
            />
            <button
              type="submit"
              className={`btn btn-primary ${s.enviar}`}
              disabled={estado.enviando || sinCuota || !texto.trim()}
              aria-busy={estado.enviando}
            >
              <Icon name="enviar" />
              <span className="sr-only">Enviar</span>
            </button>
          </div>
          <p className={s.pie} id={idAyuda}>
            <span>{cuotaTexto(estado.cuota)}</span>
            <span aria-hidden={texto.length < max * 0.8} className={texto.length > max * 0.9 ? s.contadorAlto : undefined}>
              {texto.length > max * 0.8 ? `${texto.length}/${max}` : ""}
            </span>
          </p>
          <p className={s.legal}>Orientación educativa; no reemplaza la asesoría legal. No compartas datos personales.</p>
        </form>
      )}
    </>
  );
}

function Mensaje({
  m,
  hrefBrecha,
  hrefEvidencia,
  hrefRuta,
  onSugerencia,
}: {
  m: MensajeTutorApi;
  hrefBrecha: (codigo: string) => string;
  hrefEvidencia: (respuestaId: number) => string;
  hrefRuta: (rutaId: number) => string;
  onSugerencia?: (q: string) => void;
}) {
  if (m.rol === "usuario") {
    return (
      <div className={`${s.mensaje} ${s.usuario}`} data-bloqueado={m.bloqueado || undefined}>
        <span className="sr-only">Tú dijiste: </span>
        {parrafos(m.contenido).map((p, i) => (
          <p key={i}>{p}</p>
        ))}
        {m.fecha ? <span className={s.hora}>{horaCorta(m.fecha)}</span> : null}
      </div>
    );
  }
  const tipo = TIPO_RESPUESTA[m.tipo];
  return (
    <article className={`${s.mensaje} ${s.tutor}`} data-tipo={m.tipo} aria-label={`Respuesta del tutor: ${tipo.etiqueta}`}>
      <p className={s.meta}>
        <span className={`badge tone-${tipo.tono}`}>{tipo.etiqueta}</span>
        {m.nivel ? <span className={s.metaNivel}>Nivel {m.nivel}</span> : null}
        {m.fecha ? <span className={s.hora}>{horaCorta(m.fecha)}</span> : null}
      </p>
      {parrafos(m.contenido).map((p, i) => (
        <p key={i}>{p}</p>
      ))}

      {m.pasos.length ? (
        <ol className={s.pasos} aria-label="Pasos del plan de acción">
          {m.pasos.map((p) => (
            <li key={p.orden}>
              <span className={s.pasoAccion}>{p.accion}</span>
              {p.responsable_sugerido || p.evidencia_esperada ? (
                <span className={s.pasoMeta}>
                  {p.responsable_sugerido ? (
                    <span>
                      <Icon name="usuario" />
                      {p.responsable_sugerido}
                    </span>
                  ) : null}
                  {p.evidencia_esperada ? (
                    <span>
                      <Icon name="documento" />
                      Evidencia: {p.evidencia_esperada}
                    </span>
                  ) : null}
                </span>
              ) : null}
              {onSugerencia ? (
                <button type="button" className={s.pasoExplicar} onClick={() => onSugerencia(preguntaPaso(p))}>
                  Explícame este paso<span className="sr-only">: {p.accion}</span>
                </button>
              ) : null}
            </li>
          ))}
        </ol>
      ) : null}

      {m.brechas.length ? (
        <div className={s.citadas}>
          <p className={s.citadasTitulo}>Brechas de tu evaluación</p>
          <ul>
            {m.brechas.map((b) => (
              <li key={b.ref} className={s.citada}>
                <Link href={hrefBrecha(b.codigo)} className={s.citadaCodigo}>
                  <span className="code">{b.ref}</span>
                  <span className="sr-only">: ver en el listado de brechas</span>
                </Link>
                <BadgeSeveridad severidad={b.severidad} />
                <span className={s.citadaDominio}>{b.dominio}</span>
                <span className={s.citadaLinks}>
                  {b.ruta_id ? <Link href={hrefRuta(b.ruta_id)}>Módulo</Link> : null}
                  <Link href={hrefEvidencia(b.respuesta_id)}>Subir evidencia<span className="sr-only"> para {b.ref}</span></Link>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {m.referencias_normativas.length ? (
        <p className={s.normas}>
          <Icon name="libro" />
          <span>
            <strong>{m.referencias_normativas.length === 1 ? "Fuente" : "Fuentes"} del control:</strong>{" "}
            {m.referencias_normativas.join(" · ")}
          </span>
        </p>
      ) : null}

      {m.sugerencias.length && onSugerencia ? (
        <p className={s.sugerenciasTitulo}>Puedes preguntarme:</p>
      ) : null}
      {m.sugerencias.length && onSugerencia ? (
        <ul className={s.sugerencias} aria-label="Siguientes preguntas sugeridas">
          {m.sugerencias.map((q) => (
            <li key={q}>
              <button type="button" className="chip" onClick={() => onSugerencia(q)}>
                {q}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function Historial({
  items,
  actual,
  onAbrir,
  onBorrar,
}: {
  items: ReturnType<typeof useTutor>["estado"]["conversaciones"];
  actual: number | null;
  onAbrir: (id: number) => void;
  onBorrar: (id: number) => void;
}) {
  const [confirmar, setConfirmar] = useState<number | null>(null);
  if (!items.length) {
    return (
      <div className={s.centro}>
        <Icon name="historial" width={28} height={28} />
        <p>Aún no tienes conversaciones guardadas. Se borran solas tras 30 días sin actividad.</p>
      </div>
    );
  }
  return (
    <div className={s.historial}>
      <p className={s.historialNota}>Las conversaciones se borran tras 30 días sin actividad.</p>
      <ul>
        {items.map((c) => (
          <li key={c.id} className={s.historialFila} data-actual={c.id === actual || undefined}>
            <button type="button" className={s.historialAbrir} onClick={() => onAbrir(c.id)} aria-current={c.id === actual || undefined}>
              <span className={s.historialTitulo}>{c.titulo || "Conversación sin mensajes"}</span>
              <span className={s.historialMeta}>
                {fechaLarga(c.fecha_ultimo_mensaje)} · Nivel {c.nivel} · {c.mensajes_total} mensajes
                {c.estado === "solo_lectura" ? " · evaluación anterior" : ""}
              </span>
            </button>
            {confirmar === c.id ? (
              <span className={s.confirmar}>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmar(null)}>Cancelar</button>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => { onBorrar(c.id); setConfirmar(null); }}>
                  Borrar
                </button>
              </span>
            ) : (
              <button type="button" className="icon-btn" onClick={() => setConfirmar(c.id)} aria-label={`Borrar la conversación ${c.titulo ?? c.id}`}>
                <Icon name="basura" />
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
