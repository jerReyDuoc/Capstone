"use client";

/**
 * HU-26 criterio 1 y 3 · Recorrido de un módulo del plan formativo.
 *
 *   ┌ riel de pasos ─────┐ ┌ paso actual ──────────────────────────────┐
 *   │ 1 Lección          │ │ Lección 2 de 4 · 60 min                   │
 *   │ 2 Lección (actual) │ │ contenido · material de apoyo             │
 *   │ 3 Lección          │ │ [Anterior]        [Marcar como vista y …] │
 *   │ ✓ Actividad        │ └───────────────────────────────────────────┘
 *   └────────────────────┘
 *
 * Las lecciones son una secuencia real (el número del riel es su orden). La actividad se
 * habilita al ver todas; la corrige el servidor y, aprobada, el módulo queda completado con
 * fecha y constancia. Completar NO cambia el puntaje: las brechas se cierran con evidencia
 * (HU-17), y por eso el cierre ofrece "Subir evidencia".
 */
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type RefObject } from "react";
import { Icon } from "@/components/ui/Icon";
import { BadgeSeveridad } from "@/components/ui/Basicos";
import { usePanel } from "@/hooks/usePanel";
import { descargarBlob } from "@/lib/exportar";
import {
  cargarModulo,
  descargarConstancia,
  enviarVerificacion,
  ESTADO_MODULO,
  esSinServicio,
  faltanPorResponder,
  fechaLarga,
  hrefRemediacion,
  marcarLeccionVista,
  mensajeFormacion,
  minutosTexto,
  siguienteLeccion,
} from "@/lib/formacion";
import { horasTexto } from "@/lib/planFormativo";
import type { LeccionApi, ModuloRecorridoApi, ResultadoVerificacionApi } from "@/lib/types";

type Paso = { tipo: "leccion"; orden: number } | { tipo: "actividad" } | { tipo: "cierre" };
type Estado =
  | { tipo: "cargando" }
  | { tipo: "listo"; modulo: ModuloRecorridoApi }
  | { tipo: "sin-servicio"; mensaje: string }
  | { tipo: "error"; mensaje: string };

function pasoInicial(m: ModuloRecorridoApi): Paso {
  if (m.avance.estado === "completado") return { tipo: "cierre" };
  const sig = siguienteLeccion(m.lecciones);
  if (sig != null) return { tipo: "leccion", orden: sig };
  return m.lecciones.length ? { tipo: "actividad" } : { tipo: "cierre" };
}

export function RecorridoModulo({ rutaId }: { rutaId: number | null }) {
  const { evaluacionId, modo, href } = usePanel();
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [paso, setPaso] = useState<Paso | null>(null);
  const [aviso, setAviso] = useState("");
  const tituloPaso = useRef<HTMLHeadingElement>(null);
  const moverFoco = useRef(false);

  const cargar = useCallback(async () => {
    if (rutaId == null) {
      setEstado({ tipo: "error", mensaje: "Este módulo no existe." });
      return;
    }
    try {
      const modulo = await cargarModulo(rutaId, evaluacionId);
      setEstado({ tipo: "listo", modulo });
      setPaso((p) => p ?? pasoInicial(modulo));
    } catch (e) {
      setEstado(esSinServicio(e) ? { tipo: "sin-servicio", mensaje: mensajeFormacion(e) } : { tipo: "error", mensaje: mensajeFormacion(e) });
    }
  }, [rutaId, evaluacionId]);

  useEffect(() => {
    if (modo === "detectando") return;
    void cargar();
  }, [cargar, modo]);

  // Al cambiar de paso, el foco va a su título (lectores de pantalla y teclado)
  useEffect(() => {
    if (moverFoco.current) tituloPaso.current?.focus();
    moverFoco.current = false;
  }, [paso]);

  const irA = (p: Paso) => {
    moverFoco.current = true;
    setPaso(p);
  };

  const volver = (
    <Link href={href("/panel/capacitacion")} className="volver">
      <Icon name="flechaIzq" />
      Volver a Capacitación
    </Link>
  );

  if (estado.tipo === "cargando" || (estado.tipo === "listo" && !paso)) {
    return (
      <div role="status" aria-live="polite" className="recorrido-carga">
        <span className="sr-only">Cargando el módulo…</span>
        <div className="skeleton" style={{ height: 120 }} />
        <div className="skeleton" style={{ height: 420 }} />
      </div>
    );
  }
  if (estado.tipo !== "listo") {
    return (
      <>
        {volver}
        <div className="state" role={estado.tipo === "error" ? "alert" : "status"}>
          <Icon name={estado.tipo === "sin-servicio" ? "candado" : "alerta"} width={32} height={32} style={{ color: "var(--medio)" }} />
          <h1 className="state-titulo">{estado.tipo === "sin-servicio" ? "Este módulo es parte del servicio contratado" : "No pudimos abrir el módulo"}</h1>
          <p>
            {estado.tipo === "sin-servicio" && modo !== "cliente"
              ? "Ingresa con la cuenta de tu empresa para recorrer los módulos y registrar el avance."
              : estado.mensaje}
          </p>
          {estado.tipo === "sin-servicio" && modo !== "cliente" ? (
            <Link href="/ingresar" className="btn btn-primary">Ingresar con mi empresa</Link>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => void cargar()}>
              <Icon name="refrescar" />
              Reintentar
            </button>
          )}
        </div>
      </>
    );
  }

  const m = estado.modulo;
  const actual = paso as Paso;
  const vistas = new Set(m.avance.lecciones_vistas);
  const todasVistas = m.lecciones.every((l) => vistas.has(l.orden));
  const completado = m.avance.estado === "completado";
  const actualizar = (avance: ModuloRecorridoApi["avance"]) =>
    setEstado({
      tipo: "listo",
      modulo: {
        ...m,
        avance,
        lecciones: m.lecciones.map((l) => ({ ...l, vista: avance.lecciones_vistas.includes(l.orden) })),
        actividad: { ...m.actividad, disponible: m.actividad.preguntas.length > 0 && m.lecciones.every((l) => avance.lecciones_vistas.includes(l.orden)) },
      },
    });

  return (
    <>
      {volver}
      <header className="recorrido-cabeza">
        <div className="recorrido-titulos">
          <p className="recorrido-ruta">
            {m.ruta.dominio ?? "Plan formativo"}
            {m.ruta.nivel ? <span className="nivel-chip" data-nivel={m.ruta.nivel}>{m.ruta.nivel}</span> : null}
          </p>
          <h1 className="page-title recorrido-nombre">{m.ruta.nombre}</h1>
          {m.ruta.objetivo ? <p className="page-sub">{m.ruta.objetivo}</p> : null}
        </div>
        <dl className="recorrido-datos">
          <div>
            <dt>Estado</dt>
            <dd>
              <span className={`badge tone-${ESTADO_MODULO[m.avance.estado].tono}`}>{ESTADO_MODULO[m.avance.estado].etiqueta}</span>
            </dd>
          </div>
          <div>
            <dt>Duración</dt>
            <dd>{horasTexto(m.ruta.horas)}</dd>
          </div>
          {m.ruta.modalidad ? (
            <div>
              <dt>Modalidad</dt>
              <dd>{m.ruta.modalidad}</dd>
            </div>
          ) : null}
          <div>
            <dt>Lecciones</dt>
            <dd>
              {m.avance.lecciones_vistas.length} de {m.lecciones.length}
            </dd>
          </div>
        </dl>
      </header>

      <p className="aviso-accion" role="status" aria-live="polite">
        {aviso}
      </p>

      <div className="recorrido">
        <nav className="riel" aria-label="Pasos del módulo">
          <ol>
            {m.lecciones.map((l) => (
              <li key={l.orden}>
                <button
                  type="button"
                  className="riel-paso"
                  aria-current={actual.tipo === "leccion" && actual.orden === l.orden ? "step" : undefined}
                  data-hecho={l.vista || undefined}
                  onClick={() => irA({ tipo: "leccion", orden: l.orden })}
                >
                  <span className="riel-marca" aria-hidden="true">
                    {l.vista ? <Icon name="check" /> : l.orden}
                  </span>
                  <span className="riel-texto">
                    <span className="riel-titulo">{l.titulo}</span>
                    <span className="riel-meta">
                      {l.vista ? "Vista" : "Pendiente"}
                      {minutosTexto(l.duracion_min) ? ` · ${minutosTexto(l.duracion_min)}` : ""}
                    </span>
                  </span>
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                className="riel-paso riel-actividad"
                aria-current={actual.tipo === "actividad" ? "step" : undefined}
                data-hecho={completado || undefined}
                disabled={!todasVistas && !completado}
                aria-describedby={!todasVistas && !completado ? "riel-bloqueo" : undefined}
                onClick={() => irA({ tipo: "actividad" })}
              >
                <span className="riel-marca" aria-hidden="true">
                  {completado ? <Icon name="check" /> : todasVistas ? <Icon name="diana" /> : <Icon name="candado" />}
                </span>
                <span className="riel-texto">
                  <span className="riel-titulo">Actividad de verificación</span>
                  <span className="riel-meta" id="riel-bloqueo">
                    {completado
                      ? `Aprobada · ${Math.round(m.avance.mejor_puntaje ?? 0)} / 100`
                      : todasVistas
                        ? `${m.actividad.preguntas.length} preguntas`
                        : "Se habilita al ver todas las lecciones"}
                  </span>
                </span>
              </button>
            </li>
            {completado ? (
              <li>
                <button
                  type="button"
                  className="riel-paso"
                  aria-current={actual.tipo === "cierre" ? "step" : undefined}
                  data-hecho
                  onClick={() => irA({ tipo: "cierre" })}
                >
                  <span className="riel-marca" aria-hidden="true">
                    <Icon name="constancia" />
                  </span>
                  <span className="riel-texto">
                    <span className="riel-titulo">Constancia</span>
                    <span className="riel-meta">{fechaLarga(m.avance.fecha_completado)}</span>
                  </span>
                </button>
              </li>
            ) : null}
          </ol>
        </nav>

        <section className="card recorrido-paso" aria-labelledby="paso-titulo">
          {actual.tipo === "leccion" ? (
            <PasoLeccion
              key={actual.orden}
              leccion={m.lecciones.find((l) => l.orden === actual.orden) ?? m.lecciones[0]}
              total={m.lecciones.length}
              tituloRef={tituloPaso}
              completado={completado}
              onAnterior={actual.orden > 1 ? () => irA({ tipo: "leccion", orden: actual.orden - 1 }) : null}
              onVista={async (orden) => {
                try {
                  const avance = await marcarLeccionVista(m.ruta.id, orden, m.evaluacion_id);
                  actualizar(avance);
                  const siguiente = m.lecciones.find((l) => l.orden > orden && !avance.lecciones_vistas.includes(l.orden))
                    ?? m.lecciones.find((l) => !avance.lecciones_vistas.includes(l.orden));
                  if (siguiente) {
                    setAviso(`Lección ${orden} marcada como vista.`);
                    irA({ tipo: "leccion", orden: siguiente.orden });
                  } else {
                    setAviso("Viste todas las lecciones. Ya puedes hacer la actividad de verificación.");
                    irA(completado ? { tipo: "cierre" } : { tipo: "actividad" });
                  }
                } catch (e) {
                  setAviso(mensajeFormacion(e));
                }
              }}
            />
          ) : actual.tipo === "actividad" ? (
            <PasoActividad
              modulo={m}
              tituloRef={tituloPaso}
              onResultado={(r) => {
                actualizar(r.avance);
                if (r.aprobado) {
                  setAviso(`Aprobaste con ${Math.round(r.puntaje)} de 100. Completaste el módulo.`);
                  irA({ tipo: "cierre" });
                }
              }}
              onAviso={setAviso}
            />
          ) : (
            <PasoCierre modulo={m} tituloRef={tituloPaso} onAviso={setAviso} />
          )}
        </section>
      </div>
    </>
  );
}

/* ------------------------------------------------------------ lección */
function PasoLeccion({
  leccion: l,
  total,
  tituloRef,
  completado,
  onAnterior,
  onVista,
}: {
  leccion: LeccionApi;
  total: number;
  tituloRef: RefObject<HTMLHeadingElement | null>;
  completado: boolean;
  onAnterior: (() => void) | null;
  onVista: (orden: number) => Promise<void>;
}) {
  const [guardando, setGuardando] = useState(false);
  const esUltima = l.orden === total;
  return (
    <article className="leccion">
      <p className="leccion-meta">
        Lección {l.orden} de {total}
        {minutosTexto(l.duracion_min) ? ` · ${minutosTexto(l.duracion_min)}` : ""}
      </p>
      <h2 className="leccion-titulo" id="paso-titulo" ref={tituloRef} tabIndex={-1}>
        {l.titulo}
      </h2>
      <div className="leccion-cuerpo">
        {l.contenido.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </div>

      {l.material_apoyo.length ? (
        <section className="material" aria-labelledby={`material-${l.orden}`}>
          <h3 className="material-titulo" id={`material-${l.orden}`}>Material de apoyo</h3>
          <ul className="material-lista">
            {l.material_apoyo.map((mat) => (
              <li key={mat.titulo} className="material-item">
                <Icon name={mat.tipo === "video" ? "play" : mat.tipo === "plantilla" ? "tabla" : "documento"} />
                <span>
                  <span className="material-nombre">{mat.titulo}</span>
                  {mat.descripcion ? <span className="material-desc">{mat.descripcion}</span> : null}
                </span>
                <span className="badge tone-info">En preparación</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="leccion-acciones">
        {onAnterior ? (
          <button type="button" className="btn btn-ghost" onClick={onAnterior}>
            <Icon name="flechaIzq" />
            Lección anterior
          </button>
        ) : (
          <span />
        )}
        {l.vista ? (
          <span className="leccion-hecha">
            <Icon name="check" />
            Lección vista
          </span>
        ) : (
          <button
            type="button"
            className="btn btn-primary"
            disabled={guardando}
            aria-busy={guardando}
            onClick={async () => {
              setGuardando(true);
              await onVista(l.orden);
              setGuardando(false);
            }}
          >
            {esUltima && !completado ? "Marcar como vista e ir a la actividad" : "Marcar como vista y seguir"}
            <Icon name="flecha" />
          </button>
        )}
      </div>
    </article>
  );
}

/* ------------------------------------------------------------ actividad */
function PasoActividad({
  modulo: m,
  tituloRef,
  onResultado,
  onAviso,
}: {
  modulo: ModuloRecorridoApi;
  tituloRef: RefObject<HTMLHeadingElement | null>;
  onResultado: (r: ResultadoVerificacionApi) => void;
  onAviso: (t: string) => void;
}) {
  const [elegidas, setElegidas] = useState<Record<number, number>>({});
  const [faltan, setFaltan] = useState<number[]>([]);
  const [resultado, setResultado] = useState<ResultadoVerificacionApi | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");
  const [restantes, setRestantes] = useState(m.actividad.intentos_restantes_hoy);
  const idForm = useId();
  const resumen = useRef<HTMLDivElement>(null);
  const a = m.actividad;

  if (m.avance.estado === "completado") {
    return (
      <div className="actividad">
        <h2 className="leccion-titulo" id="paso-titulo" ref={tituloRef} tabIndex={-1}>Actividad aprobada</h2>
        <p className="card-sub">
          Aprobaste con {Math.round(m.avance.mejor_puntaje ?? 0)} de 100 el {fechaLarga(m.avance.fecha_completado)}.
        </p>
      </div>
    );
  }

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const pendientes = faltanPorResponder(a.preguntas, elegidas);
    setFaltan(pendientes);
    if (pendientes.length) {
      setError(`Te ${pendientes.length === 1 ? "falta 1 pregunta" : `faltan ${pendientes.length} preguntas`} por responder.`);
      requestAnimationFrame(() => resumen.current?.focus());
      return;
    }
    setError("");
    setEnviando(true);
    try {
      const r = await enviarVerificacion(m.ruta.id, elegidas, m.evaluacion_id);
      setResultado(r);
      setRestantes(r.intentos_restantes_hoy);
      onResultado(r);
      if (!r.aprobado) {
        // El resultado se anuncia en el resumen del formulario (aria-live); el aviso de la página queda limpio
        onAviso("");
        requestAnimationFrame(() => resumen.current?.focus());
      }
    } catch (err) {
      setError(mensajeFormacion(err));
      requestAnimationFrame(() => resumen.current?.focus());
    } finally {
      setEnviando(false);
    }
  };

  const correcta = (id: number) => resultado?.detalle.find((d) => d.pregunta_id === id)?.correcta;
  const sinIntentos = restantes === 0;

  return (
    <form className="actividad" onSubmit={enviar} aria-describedby={`${idForm}-intro`} noValidate>
      <p className="leccion-meta">Actividad de verificación</p>
      <h2 className="leccion-titulo" id="paso-titulo" ref={tituloRef} tabIndex={-1}>
        Comprueba lo que aprendiste
      </h2>
      <p className="card-sub" id={`${idForm}-intro`}>
        {a.preguntas.length} preguntas de selección única. Apruebas con {Math.round(a.umbral_aprobacion)} de 100
        {restantes != null ? ` · te quedan ${restantes} de ${a.intentos_por_dia} intentos hoy` : ""}.
      </p>

      <div ref={resumen} tabIndex={-1} className="actividad-resumen" aria-live="polite">
        {error ? (
          <p className="dialogo-error">
            <Icon name="alerta" />
            {error}
          </p>
        ) : null}
        {resultado && !resultado.aprobado ? (
          <p className="resultado-no">
            <Icon name="info" />
            <span>
              <strong>
                {resultado.correctas} de {resultado.total} correctas ({Math.round(resultado.puntaje)} / 100).
              </strong>{" "}
              Necesitas {Math.round(resultado.umbral_aprobacion)} para aprobar. Repasa las lecciones de las preguntas marcadas y
              vuelve a enviar.
            </span>
          </p>
        ) : null}
      </div>

      <ol className="preguntas">
        {a.preguntas.map((p, i) => {
          const ok = correcta(p.id);
          const pendiente = faltan.includes(p.id);
          return (
            <li key={p.id}>
              <fieldset
                className="pregunta"
                data-resultado={ok === undefined ? undefined : ok ? "ok" : "mal"}
                aria-invalid={pendiente || undefined}
                aria-describedby={pendiente ? `${idForm}-p${p.id}-falta` : ok === false ? `${idForm}-p${p.id}-mal` : undefined}
              >
                <legend>
                  <span className="pregunta-num">{i + 1}.</span> {p.enunciado}
                </legend>
                {p.opciones.map((o) => (
                  <label key={o.id} className="opcion">
                    <input
                      type="radio"
                      name={`${idForm}-p${p.id}`}
                      value={o.id}
                      checked={elegidas[p.id] === o.id}
                      onChange={() => {
                        setElegidas((x) => ({ ...x, [p.id]: o.id }));
                        setFaltan((f) => f.filter((id) => id !== p.id));
                      }}
                    />
                    <span>{o.texto}</span>
                  </label>
                ))}
                {pendiente ? (
                  <p className="pregunta-nota" id={`${idForm}-p${p.id}-falta`}>Elige una respuesta.</p>
                ) : ok === false ? (
                  <p className="pregunta-nota" id={`${idForm}-p${p.id}-mal`}>
                    <Icon name="cerrar" /> Respuesta incorrecta
                  </p>
                ) : ok ? (
                  <p className="pregunta-nota pregunta-ok">
                    <Icon name="check" /> Correcta
                  </p>
                ) : null}
              </fieldset>
            </li>
          );
        })}
      </ol>

      <div className="leccion-acciones">
        <span className="card-sub">{sinIntentos ? "Usaste los intentos de hoy. Vuelve mañana." : ""}</span>
        <button type="submit" className="btn btn-primary" disabled={enviando || sinIntentos} aria-busy={enviando}>
          {enviando ? "Corrigiendo…" : resultado ? "Enviar de nuevo" : "Enviar respuestas"}
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------ cierre y constancia */
function PasoCierre({
  modulo: m,
  tituloRef,
  onAviso,
}: {
  modulo: ModuloRecorridoApi;
  tituloRef: RefObject<HTMLHeadingElement | null>;
  onAviso: (t: string) => void;
}) {
  const [bajando, setBajando] = useState(false);
  const completado = m.avance.estado === "completado";
  if (!completado) {
    return (
      <div className="actividad">
        <h2 className="leccion-titulo" id="paso-titulo" ref={tituloRef} tabIndex={-1}>Este módulo aún no tiene lecciones</h2>
        <p className="card-sub">Therion Labs está preparando su contenido. Vuelve pronto.</p>
      </div>
    );
  }
  return (
    <div className="cierre">
      <div className="cierre-sello" aria-hidden="true">
        <Icon name="constancia" />
      </div>
      <h2 className="leccion-titulo" id="paso-titulo" ref={tituloRef} tabIndex={-1}>
        Completaste el módulo
      </h2>
      <p className="cierre-texto">
        Tu empresa completó <strong>{m.ruta.nombre}</strong> el {fechaLarga(m.avance.fecha_completado)}, con{" "}
        {Math.round(m.avance.mejor_puntaje ?? 0)} de 100 en la actividad de verificación.
      </p>
      <dl className="cierre-codigo">
        <dt>Código de la constancia</dt>
        <dd>{m.avance.codigo_constancia}</dd>
      </dl>
      <button
        type="button"
        className="btn btn-primary"
        disabled={bajando}
        aria-busy={bajando}
        onClick={async () => {
          setBajando(true);
          onAviso("Generando la constancia…");
          try {
            const { blob, nombre } = await descargarConstancia(m.ruta.id);
            descargarBlob(blob, nombre);
            onAviso(`Descargamos ${nombre}.`);
          } catch (e) {
            onAviso(mensajeFormacion(e));
          } finally {
            setBajando(false);
          }
        }}
      >
        <Icon name="descargar" />
        Descargar constancia (PDF)
      </button>

      {m.brechas.length ? (
        <section className="cierre-brechas" aria-labelledby="cierre-brechas-t">
          <h3 className="material-titulo" id="cierre-brechas-t">El siguiente paso: cerrar las brechas</h3>
          <p className="card-sub">
            La formación quedó registrada, pero el puntaje de madurez solo cambia cuando subes evidencia de que el control ya se
            aplica en tu organización.
          </p>
          <ul className="cierre-lista">
            {m.brechas.map((b) => (
              <li key={b.codigo}>
                <span className="code">{b.codigo}</span>
                <BadgeSeveridad severidad={b.severidad} />
                <span className="cierre-estado">Formación hecha · falta evidencia</span>
                {b.respuesta_id ? (
                  <Link className="btn btn-ghost btn-sm" href={hrefRemediacion(m.evaluacion_id, b.respuesta_id)}>
                    <Icon name="subir" />
                    Subir evidencia<span className="sr-only"> de {b.codigo}</span>
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
