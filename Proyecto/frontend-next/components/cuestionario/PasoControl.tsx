"use client";

/**
 * HU-01 / HU-02 · Un control de la matriz: estado de cumplimiento (5 estados), justificación
 * (opcional en todos los estados desde las correcciones 05-11) y evidencia que valida la IA
 * (obligatoria en "Cumplido" y, para completar, en "Requiere revisión"). "Guardar y continuar" hace upsert de la respuesta y, si hay archivo, lo sube;
 * la validación con IA sigue en segundo plano y su resultado se ve al volver al control.
 *
 * Distribución (para no tener que bajar con la rueda a cada rato):
 *  - Las 5 opciones son compactas (una grilla de botones); la ayuda de cada una se muestra
 *    en una sola línea al pasar por encima, al enfocarla o al elegirla.
 *  - Con espacio suficiente (container query de la tarjeta) la pregunta va a la izquierda y
 *    la respuesta a la derecha; en pantallas angostas, una debajo de la otra.
 *  - Al elegir un estado la vista baja sola hasta la justificación, y la barra de
 *    "Guardar y continuar" queda siempre visible (sticky) al pie de la tarjeta.
 *  - Atajos: 1 a 5 eligen el estado (fuera de un campo de texto) y Ctrl/⌘ + Enter guarda y continúa.
 *
 * Correcciones 29-10: para el usuario cada control es una "pregunta" y no se muestra su código
 * interno (DAT-001…), que expone la documentación de Therion Labs.
 */
import { useEffect, useId, useRef, useState } from "react";
import { AvisoError } from "@/components/inicio/AvisoError";
import { BadgeImpacto } from "@/components/ui/Basicos";
import { CampoArchivo } from "@/components/ui/CampoArchivo";
import { Icon } from "@/components/ui/Icon";
import { normalizarCriticidad } from "@/lib/madurez";
import type { Cuestionario } from "@/hooks/useCuestionario";
import { subirEvidencia } from "@/lib/cuestionario/api";
import {
  errorArchivoEvidencia,
  errorJustificacion,
  ESTADO_POR_VALOR,
  ESTADOS,
  esEstadoDeclarado,
  EXTENSIONES_EVIDENCIA,
  JUSTIFICACION_MIN,
  normalizarJustificacion,
  type ControlAplicableApi,
  type EstadoDeclarado,
  type RespuestaDetalleApi,
} from "@/lib/cuestionario/modelo";
import { comoErrorEncuesta } from "@/lib/encuesta/cliente";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";
import { ListaEvidencias, useSeguimientoEvidencias } from "./Evidencias";
import s from "./cuestionario.module.css";

/** Auditoría UX 16-11: las cuatro respuestas; "Requiere revisión" va como acción aparte. */
const ESTADO_REVISION: EstadoDeclarado = "requiere_revision";
const OPCIONES_PRINCIPALES = ESTADOS.filter((o) => o.valor !== ESTADO_REVISION);

interface Props {
  c: Cuestionario;
  control: ControlAplicableApi;
  /** Llamar tras subir una evidencia o recibir un 429 de cuota (actualiza el banner). */
  onLimites: () => void;
}

export function PasoControl({ c, control, onLimites }: Props) {
  const previa = c.respondidas.get(control.id_control);
  const [detalle, setDetalle] = useState<RespuestaDetalleApi | null>(null);
  const [cargandoPrevia, setCargandoPrevia] = useState(Boolean(previa));
  const [estado, setEstado] = useState<EstadoDeclarado | null>(previa && esEstadoDeclarado(previa.estado) ? previa.estado : null);
  const [justificacion, setJustificacion] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [errorArchivo, setErrorArchivo] = useState<string | null>(null);
  const [tocado, setTocado] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<ErrorEncuesta | null>(null);
  const [guardadoSinAvanzar, setGuardadoSinAvanzar] = useState(false);
  const titulo = useRef<HTMLHeadingElement>(null);
  const inputArchivo = useRef<HTMLInputElement>(null);
  const campoJustificacion = useRef<HTMLDivElement>(null);
  const elegidoPorUsuario = useRef(false);
  const ids = { just: useId(), ayudaJust: useId(), errJust: useId(), archivo: useId(), ayudaArchivo: useId(), opcion: useId() };

  const evidencias = useSeguimientoEvidencias(detalle?.evidencias ?? [], () => {
    if (previa) void c.obtenerDetalle(previa.idRespuesta, true).then(setDetalle).catch(() => undefined);
  });

  // Foco al título al cambiar de control (navegación por teclado / lector de pantalla)
  useEffect(() => {
    titulo.current?.focus({ preventScroll: false });
  }, []);

  // Respuesta previa: estado, justificación (ya anonimizada) y evidencias
  useEffect(() => {
    if (!previa) return;
    let vigente = true;
    c.obtenerDetalle(previa.idRespuesta)
      .then((d) => {
        if (!vigente) return;
        setDetalle(d);
        if (esEstadoDeclarado(d.estado_clasificacion)) setEstado(d.estado_clasificacion);
        setJustificacion(d.justificacion_usuario ?? "");
      })
      .catch(() => undefined) // sin detalle se puede responder igual
      .finally(() => vigente && setCargandoPrevia(false));
    return () => {
      vigente = false;
    };
    // solo al montar este control
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Al elegir un estado, la justificación (y la evidencia) quedan a la vista sin usar la rueda
  useEffect(() => {
    if (!estado || !elegidoPorUsuario.current) return;
    elegidoPorUsuario.current = false;
    const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Solo lo necesario para ver la justificación (las opciones siguen a la vista si caben)
    campoJustificacion.current?.scrollIntoView({ block: "nearest", behavior: sinMovimiento ? "auto" : "smooth" });
  }, [estado]);

  const opcion = estado ? ESTADO_POR_VALOR[estado] : null;
  // Auditoría UX 16-11 · Fase 9.2: la descripción solo de la opción ELEGIDA (antes aparecía al pasar
  // el mouse y la opción parecía elegida).
  const ayudaVisible = estado ? ESTADO_POR_VALOR[estado] : null;
  const pideRevision = estado === ESTADO_REVISION;
  const errJust = estado ? errorJustificacion(estado, justificacion) : null;
  const largo = normalizarJustificacion(justificacion).length;
  const tieneEvidencias = (detalle?.evidencias.length ?? 0) > 0;
  const faltaEvidenciaRevision = estado === "requiere_revision" && !archivo && !tieneEvidencias;
  // Correcciones 05-11: "Cumplido" no se guarda sin un documento que lo respalde
  const faltaEvidenciaCumplido = estado === "cumplido" && !archivo && !tieneEvidencias;
  const posicion = c.controles.findIndex((x) => x.id_control === control.id_control);
  const total = c.controles.length;
  const todosRespondidos = (c.progreso?.controles_pendientes ?? 1) === 0;

  function elegirEstado(valor: EstadoDeclarado) {
    elegidoPorUsuario.current = true;
    setEstado(valor);
    setGuardadoSinAvanzar(false);
    if (!ESTADO_POR_VALOR[valor].admiteEvidencia) elegirArchivo(null);
  }

  function elegirArchivo(f: File | null) {
    setErrorArchivo(null);
    if (!f) {
      setArchivo(null);
      return;
    }
    const e = errorArchivoEvidencia(f);
    if (e) {
      setErrorArchivo(e);
      setArchivo(null);
      if (inputArchivo.current) inputArchivo.current.value = "";
      return;
    }
    setArchivo(f);
  }

  async function guardar(avanzar: boolean) {
    setTocado(true);
    setError(null);
    setGuardadoSinAvanzar(false);
    if (!estado || errJust) return;
    if (faltaEvidenciaCumplido) {
      setErrorArchivo("Adjunta un documento que respalde que esto se cumple, o elige otro estado.");
      document.getElementById(ids.archivo)?.closest(`.${s.evidencia}`)?.scrollIntoView({ block: "nearest" });
      return;
    }
    setGuardando(true);
    try {
      const idRespuesta = await c.guardar(control, estado, justificacion);
      if (archivo && opcion?.admiteEvidencia) {
        try {
          await subirEvidencia(idRespuesta, archivo);
          onLimites();
        } catch (e) {
          // La respuesta quedó guardada; el archivo no. Se queda en el control para decidir.
          const info = comoErrorEncuesta(e);
          if (info.codigo.startsWith("CUOTA_") || info.codigo.startsWith("LIMITE_")) onLimites();
          setError(info);
          setDetalle(await c.obtenerDetalle(idRespuesta, true).catch(() => null));
          setGuardando(false);
          setGuardadoSinAvanzar(true);
          return;
        }
      }
      if (avanzar) {
        c.avanzar(posicion, control.id_control);
      } else {
        setArchivo(null);
        if (inputArchivo.current) inputArchivo.current.value = "";
        setDetalle(await c.obtenerDetalle(idRespuesta, true).catch(() => null));
        setGuardadoSinAvanzar(true);
        setGuardando(false);
      }
    } catch (e) {
      setError(comoErrorEncuesta(e));
      setGuardando(false);
    }
  }

  // Atajos de teclado. Se lee la versión vigente de guardar() desde una ref.
  const guardarVigente = useRef(guardar);
  guardarVigente.current = guardar;
  const guardandoVigente = useRef(guardando);
  guardandoVigente.current = guardando;
  useEffect(() => {
    function alTeclear(e: KeyboardEvent) {
      if (guardandoVigente.current || e.altKey) return;
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        void guardarVigente.current(true);
        return;
      }
      if (e.ctrlKey || e.metaKey) return;
      const destino = e.target as HTMLElement | null;
      const escribiendo =
        destino?.tagName === "TEXTAREA" ||
        destino?.isContentEditable ||
        (destino?.tagName === "INPUT" && !["radio", "checkbox", "file"].includes((destino as HTMLInputElement).type));
      if (escribiendo) return;
      const n = Number(e.key);
      if (Number.isInteger(n) && n >= 1 && n <= OPCIONES_PRINCIPALES.length) {
        e.preventDefault();
        elegirEstado(OPCIONES_PRINCIPALES[n - 1].valor);
      }
    }
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
    // elegirEstado solo usa setters estables y refs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className={`card ${s.pregunta}`} aria-labelledby="t-control" aria-busy={cargandoPrevia}>
      <div className={s.planteamiento}>
        <div className={s.cabecera}>
          {/* Auditoría UX 16-11: mismo vocabulario que Brechas ("Impacto alto"), no "Criticidad alta" */}
          {control.criticidad ? <BadgeImpacto criticidad={normalizarCriticidad(control.criticidad)} /> : null}
          <span className={s.dominio}>{control.dominio?.nombre_dominio}</span>
          <span className={`${s.dominio} ${s.alDerecha}`}>
            Pregunta {posicion + 1} de {total}
          </span>
        </div>

        <h2 id="t-control" ref={titulo} tabIndex={-1} className={s.textoPregunta}>
          {control.pregunta_evaluacion}
        </h2>

        <div className={s.contexto}>
          {control.obligacion ? (
            <div className={s.dato}>
              <span className={s.datoEtiqueta}>Qué se exige</span>
              <p>{control.obligacion}</p>
            </div>
          ) : null}
          {control.evidencia_esperada ? (
            <div className={s.dato}>
              <span className={s.datoEtiqueta}>Evidencia esperada</span>
              <p>{control.evidencia_esperada}</p>
            </div>
          ) : null}
        </div>

        {control.framework_fuente ? (
          <details className={s.normativa}>
            <summary>
              <Icon name="libro" />
              Base normativa
            </summary>
            <dl>
              <dt>Fuente</dt>
              <dd>{control.framework_fuente}{control.articulo_referencia ? ` — ${control.articulo_referencia}` : ""}</dd>
              {control.tipo_fuente ? (
                <>
                  <dt>Tipo</dt>
                  <dd>{control.tipo_fuente}</dd>
                </>
              ) : null}
              {control.aplicabilidad ? (
                <>
                  <dt>Aplica</dt>
                  <dd>{control.aplicabilidad}</dd>
                </>
              ) : null}
            </dl>
          </details>
        ) : null}
      </div>

      <div className={s.respuesta}>
        <fieldset className={s.opciones} aria-invalid={tocado && !estado ? true : undefined}>
          <legend>¿En qué estado está esto en tu organización?</legend>
          <div className={s.chips}>
            {OPCIONES_PRINCIPALES.map((o, n) => (
              <label key={o.valor} className={s.chip}>
                <input
                  type="radio"
                  name={`estado-${control.id_control}`}
                  value={o.valor}
                  aria-labelledby={`${ids.opcion}-${o.valor}`}
                  aria-describedby={`${ids.opcion}-${o.valor}-ayuda`}
                  checked={estado === o.valor}
                  onChange={() => elegirEstado(o.valor)}
                />
                <span className={s.marca} data-tono={o.tono} aria-hidden="true" />
                <span className={s.chipEtiqueta} id={`${ids.opcion}-${o.valor}`}>{o.etiqueta}</span>
                {/* Elegida = relleno + check visible (no solo el borde) */}
                <Icon name="check" className={s.chipCheck} aria-hidden="true" />
                <kbd className={s.atajo} aria-hidden="true">{n + 1}</kbd>
                <span className="sr-only" id={`${ids.opcion}-${o.valor}-ayuda`}>{o.ayuda}</span>
              </label>
            ))}
          </div>
          <p className={s.ayudaOpcion} aria-hidden="true">
            {ayudaVisible && !pideRevision ? (
              <>
                <span className={s.marca} data-tono={ayudaVisible.tono} />
                <span><strong>{ayudaVisible.etiqueta}:</strong> {ayudaVisible.ayuda}</span>
              </>
            ) : null}
          </p>
          {/* Auditoría UX 16-11 · Fase 9.3: "Requiere revisión" deja de ser una respuesta más; es una
              acción aparte. Se envía el MISMO valor al backend (estado_clasificacion = "requiere_revision"). */}
          <button
            type="button"
            className={`btn btn-ghost btn-sm ${s.botonRevision}`}
            aria-pressed={pideRevision}
            onClick={() => elegirEstado(ESTADO_REVISION)}
          >
            <Icon name={pideRevision ? "check" : "lupaMas"} aria-hidden="true" />
            No estoy seguro, que lo revise la IA
          </button>
          {pideRevision ? (
            <p className={s.ayuda}>{ESTADO_POR_VALOR[ESTADO_REVISION].ayuda}</p>
          ) : null}
          {tocado && !estado ? <p className={s.errorCampo} role="alert">Elige un estado para continuar.</p> : null}
          <p className={s.atajos} aria-hidden="true">
            Atajos: <kbd>1</kbd>–<kbd>{OPCIONES_PRINCIPALES.length}</kbd> eligen el estado y <kbd>Ctrl</kbd> + <kbd>Enter</kbd> guarda y continúa.
          </p>
        </fieldset>

        <div className={s.detalles}>
          {estado ? (
            <div ref={campoJustificacion} className={s.campo}>
              <label htmlFor={ids.just} className={s.campoEtiqueta}>
                <span>
                  Justificación{" "}
                  {opcion?.justificacionObligatoria ? <span className={s.requerido}>(obligatoria)</span> : <span className={s.opcional}>(opcional)</span>}
                </span>
                {opcion?.justificacionObligatoria ? (
                  <span className={`${s.contador} ${largo >= JUSTIFICACION_MIN ? s.contadorOk : ""}`} aria-hidden="true">
                    {largo}/{JUSTIFICACION_MIN}
                  </span>
                ) : null}
              </label>
              <textarea
                id={ids.just}
                className={s.textarea}
                value={justificacion}
                maxLength={2200}
                onChange={(e) => {
                  setJustificacion(e.target.value);
                  setGuardadoSinAvanzar(false);
                }}
                onBlur={() => justificacion && setTocado(true)}
                aria-invalid={tocado && errJust ? true : undefined}
                aria-describedby={`${ids.ayudaJust}${tocado && errJust ? ` ${ids.errJust}` : ""}`}
                placeholder={
                  opcion?.justificacionObligatoria
                    ? "Describe qué existe hoy y qué falta para cumplirlo por completo."
                    : "Contexto que ayude a interpretar tu respuesta."
                }
              />
              <p id={ids.ayudaJust} className={s.ayuda}>
                Evita nombres, RUT o correos: se anonimizan antes de guardarse y nunca llegan a la IA.
              </p>
              {tocado && errJust ? (
                <p id={ids.errJust} className={s.errorCampo} role="alert">{errJust}</p>
              ) : null}
            </div>
          ) : null}

          {opcion?.admiteEvidencia ? (
            <div className={s.evidencia}>
              <div className={s.campoEtiqueta}>
                <span>
                  Evidencia{" "}
                  {estado === "cumplido" ? (
                    <span className={s.requerido}>(obligatoria)</span>
                  ) : opcion.evidenciaObligatoria ? (
                    <span className={s.requerido}>(necesaria para completar)</span>
                  ) : (
                    <span className={s.opcional}>(opcional, mejora la precisión)</span>
                  )}
                </span>
              </div>
              <CampoArchivo
                ref={inputArchivo}
                id={ids.archivo}
                accept={EXTENSIONES_EVIDENCIA.join(",")}
                archivo={archivo}
                describedBy={ids.ayudaArchivo}
                error={errorArchivo}
                onCambiar={(f) => {
                  elegirArchivo(f);
                  if (!f && inputArchivo.current) inputArchivo.current.value = "";
                }}
              />
              <p id={ids.ayudaArchivo} className={s.ayuda}>
                Formatos: {EXTENSIONES_EVIDENCIA.join(", ")} · máx. 12 MB. La IA revisa si el documento respalda el estado que declaraste.
              </p>

              {faltaEvidenciaRevision ? (
                <p className={s.ayuda} role="note">
                  Sin evidencia, esta pregunta quedará pendiente y no podrás completar la evaluación hasta adjuntarla o cambiar el estado.
                </p>
              ) : null}
              <ListaEvidencias evidencias={evidencias} />
            </div>
          ) : null}

          {error ? <AvisoError error={error} onReintentar={() => guardar(false)} /> : null}
        </div>

        <div className={s.acciones}>
          {/* Auditoría UX 16-11 · Fase 9.4: sin "Anterior" en la primera pregunta */}
          {posicion > 0 ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => c.irA(posicion - 1)} disabled={guardando}>
              <Icon name="flecha" className={s.flechaAtras} />
              <span className={s.textoAnterior}>Anterior</span>
            </button>
          ) : <span aria-hidden="true" />}
          {guardadoSinAvanzar ? (
            <span className={s.guardado} role="status">
              <Icon name="check" />
              Respuesta guardada
            </span>
          ) : null}
          <div className={s.accionesDerecha}>
            {previa || todosRespondidos ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => guardar(false)} disabled={guardando}>
                Guardar
              </button>
            ) : null}
            <button type="button" className="btn btn-primary" onClick={() => guardar(true)} disabled={guardando} aria-busy={guardando}>
              {guardando ? (archivo ? "Subiendo evidencia…" : "Guardando…") : "Guardar y continuar"}
              {!guardando ? <Icon name="flecha" /> : null}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
