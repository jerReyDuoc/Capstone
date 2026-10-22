"use client";

/**
 * HU-01 / HU-02 · Un control de la matriz: estado de cumplimiento (5 estados), justificación
 * (obligatoria en "Parcialmente cumplido" y "Requiere revisión") y evidencia opcional que
 * valida la IA. "Guardar y continuar" hace upsert de la respuesta y, si hay archivo, lo sube;
 * la validación con IA sigue en segundo plano y su resultado se ve al volver al control.
 */
import { useEffect, useId, useRef, useState } from "react";
import { AvisoError } from "@/components/inicio/AvisoError";
import { Icon } from "@/components/ui/Icon";
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

  const opcion = estado ? ESTADO_POR_VALOR[estado] : null;
  const errJust = estado ? errorJustificacion(estado, justificacion) : null;
  const largo = normalizarJustificacion(justificacion).length;
  const tieneEvidencias = (detalle?.evidencias.length ?? 0) > 0;
  const faltaEvidenciaRevision = estado === "requiere_revision" && !archivo && !tieneEvidencias;
  const posicion = c.controles.findIndex((x) => x.id_control === control.id_control);
  const total = c.controles.length;
  const todosRespondidos = (c.progreso?.controles_pendientes ?? 1) === 0;

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

  return (
    <section className={`card ${s.pregunta}`} aria-labelledby="t-control" aria-busy={cargandoPrevia}>
      <div className={s.cabecera}>
        <span className={s.codigo}>{control.codigo_control}</span>
        {control.criticidad ? (
          <span className={`badge tone-${control.criticidad === "Alta" ? "alto" : control.criticidad === "Media" ? "medio" : "bajo"}`}>
            Criticidad {control.criticidad.toLowerCase()}
          </span>
        ) : null}
        <span className={s.dominio}>{control.dominio?.nombre_dominio}</span>
        <span className={s.dominio} style={{ marginLeft: "auto" }}>
          Control {posicion + 1} de {total}
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

      <fieldset className={s.opciones} aria-invalid={tocado && !estado ? true : undefined}>
        <legend>¿Cuál es el estado de este control en tu organización?</legend>
        {ESTADOS.map((o) => (
          <label key={o.valor} className={s.opcion}>
            <input
              type="radio"
              name={`estado-${control.id_control}`}
              value={o.valor}
              aria-labelledby={`${ids.opcion}-${o.valor}`}
              aria-describedby={`${ids.opcion}-${o.valor}-ayuda`}
              checked={estado === o.valor}
              onChange={() => {
                setEstado(o.valor);
                setGuardadoSinAvanzar(false);
                if (!o.admiteEvidencia) elegirArchivo(null);
              }}
            />
            <span className={s.opcionEtiqueta} id={`${ids.opcion}-${o.valor}`}>
              <span className={s.marca} data-tono={o.tono} aria-hidden="true" />
              {o.etiqueta}
            </span>
            <span className={s.opcionAyuda} id={`${ids.opcion}-${o.valor}-ayuda`}>{o.ayuda}</span>
          </label>
        ))}
        {tocado && !estado ? <p className={s.errorCampo} role="alert">Elige un estado para continuar.</p> : null}
      </fieldset>

      {estado ? (
        <div className={s.campo}>
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
              {opcion.evidenciaObligatoria ? <span className={s.requerido}>(necesaria para completar)</span> : <span className={s.opcional}>(opcional, mejora la precisión)</span>}
            </span>
          </div>
          <div className={s.archivo}>
            <input
              ref={inputArchivo}
              id={ids.archivo}
              type="file"
              accept={EXTENSIONES_EVIDENCIA.join(",")}
              aria-describedby={ids.ayudaArchivo}
              onChange={(e) => elegirArchivo(e.target.files?.[0] ?? null)}
            />
            <label htmlFor={ids.archivo} className={`btn btn-ghost btn-sm ${s.btnArchivo}`}>
              <Icon name="descargar" style={{ transform: "rotate(180deg)" }} />
              {archivo ? "Cambiar archivo" : "Seleccionar archivo"}
            </label>
            <span className={s.nombreArchivo}>{archivo ? archivo.name : "Ningún archivo seleccionado"}</span>
          </div>
          <p id={ids.ayudaArchivo} className={s.ayuda}>
            Formatos: {EXTENSIONES_EVIDENCIA.join(", ")} · máx. 12 MB. La IA revisa si el documento respalda el estado que declaraste.
          </p>
          {errorArchivo ? <p className={s.errorCampo} role="alert">{errorArchivo}</p> : null}
          {faltaEvidenciaRevision ? (
            <p className={s.ayuda} role="note">
              Sin evidencia, este control quedará pendiente y no podrás completar la evaluación hasta adjuntarla o cambiar el estado.
            </p>
          ) : null}
          <ListaEvidencias evidencias={evidencias} />
        </div>
      ) : null}

      {error ? <AvisoError error={error} onReintentar={() => guardar(false)} /> : null}

      <div className={s.acciones}>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => c.irA(posicion - 1)}
          disabled={posicion <= 0 || guardando}
        >
          <Icon name="flecha" style={{ transform: "rotate(180deg)" }} />
          Anterior
        </button>
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
    </section>
  );
}
