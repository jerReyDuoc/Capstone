"use client";

/**
 * HU-01 · Preguntas iniciales F1–F7. Se responden de a una y adaptan el cuestionario:
 *   - F1 = NO  → la organización no usa IA: ningún control aplica y el resto no se pregunta.
 *   - F2..F7 = SÍ suman controles específicos (datos sensibles, terceros, LLM, agentes…).
 * Al final se muestra el resumen y se guarda todo junto (el backend exige las 7).
 *
 * Distribución: la pregunta a la izquierda con dos botones grandes (Sí / No, atajos S y N) y,
 * a la derecha, "Tus respuestas", para volver a cualquier pregunta con un clic. En pantallas
 * angostas el resumen va debajo.
 *
 * Correcciones 29-10: ya no se muestra cuántos controles aplican ni qué activa cada respuesta
 * (es metodología interna): el usuario solo responde sí o no.
 */
import { useEffect, useId, useRef, useState } from "react";
import { AvisoError } from "@/components/inicio/AvisoError";
import { Icon } from "@/components/ui/Icon";
import type { Cuestionario } from "@/hooks/useCuestionario";
import {
  controlesEstimados,
  cuerpoFiltro,
  PREGUNTA_RAIZ,
  preguntasVisibles,
} from "@/lib/cuestionario/modelo";
import { ayudaFiltro, preguntas as nPreguntas } from "@/lib/cuestionario/textos";
import { comoErrorEncuesta } from "@/lib/encuesta/cliente";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";
import s from "./cuestionario.module.css";

const OPCIONES = [
  { valor: true, etiqueta: "Sí", tecla: "S" },
  { valor: false, etiqueta: "No", tecla: "N" },
] as const;

export function PasoFiltro({ c }: { c: Cuestionario }) {
  const { filtro, respuestasFiltro: resp, setRespuestasFiltro, progreso } = c;
  const preguntas = preguntasVisibles(filtro?.preguntas ?? [], resp);
  const primeraSinResponder = preguntas.findIndex((p) => resp[p.codigo] === undefined);
  const [paso, setPaso] = useState(primeraSinResponder === -1 ? preguntas.length : primeraSinResponder);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<ErrorEncuesta | null>(null);
  const titulo = useRef<HTMLHeadingElement>(null);
  const idAyuda = useId();

  // El foco sigue a la pregunta para lectores de pantalla y teclado (no en la carga inicial)
  const montado = useRef(false);
  useEffect(() => {
    if (montado.current) titulo.current?.focus();
    montado.current = true;
  }, [paso]);

  const total = preguntas.length;
  const enResumen = paso >= total;
  const pregunta = enResumen ? null : preguntas[paso];

  function responder(codigo: string, valor: boolean) {
    if (!filtro) return;
    const nuevas = { ...resp, [codigo]: valor };
    setRespuestasFiltro(nuevas);
    setError(null);
    // Pequeña pausa para que se vea la selección antes de pasar a la siguiente
    window.setTimeout(() => {
      const visibles = preguntasVisibles(filtro.preguntas, nuevas);
      const actual = visibles.findIndex((p) => p.codigo === codigo);
      setPaso(actual + 1);
    }, 180);
  }

  // Atajos S / N (fuera de un campo de texto). Se lee la pregunta vigente desde una ref.
  const preguntaVigente = useRef(pregunta?.codigo ?? null);
  preguntaVigente.current = pregunta?.codigo ?? null;
  const responderVigente = useRef(responder);
  responderVigente.current = responder;
  useEffect(() => {
    function alTeclear(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey || !preguntaVigente.current) return;
      const destino = e.target as HTMLElement | null;
      if (destino?.tagName === "TEXTAREA" || destino?.isContentEditable ||
          (destino?.tagName === "INPUT" && (destino as HTMLInputElement).type !== "radio")) return;
      const tecla = e.key.toLowerCase();
      if (tecla === "s" || tecla === "n") {
        e.preventDefault();
        responderVigente.current(preguntaVigente.current, tecla === "s");
      }
    }
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, []);

  if (!filtro) return null;
  const estimado = controlesEstimados(resp);
  const yaHabiaRespuestas = (progreso?.controles_respondidos ?? 0) > 0;
  const ayuda = pregunta ? ayudaFiltro(pregunta.codigo, pregunta.descripcion) : null;

  async function confirmar() {
    setEnviando(true);
    setError(null);
    try {
      await c.enviarFiltro(cuerpoFiltro(filtro!.preguntas, resp));
    } catch (e) {
      setError(comoErrorEncuesta(e));
      setEnviando(false);
    }
  }

  return (
    <section className={`card ${s.filtro}`} aria-labelledby="t-filtro">
      <div className={s.filtroCabecera}>
        <span className={s.filtroEtapa}>Contexto de tu organización</span>
        <span className={s.filtroCuenta}>
          {enResumen ? "Revisión" : <>Pregunta <strong>{paso + 1}</strong> de <strong>{total}</strong></>}
        </span>
      </div>
      {/* Avance segmentado: una marca por pregunta (es una secuencia real) */}
      <div
        className={s.segmentos}
        role="progressbar"
        aria-label="Avance de las preguntas iniciales"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={Math.min(paso, total)}
      >
        {preguntas.map((p, i) => (
          <span key={p.codigo} data-estado={i < paso ? "hecho" : i === paso ? "actual" : "pendiente"} />
        ))}
      </div>

      <div className={s.filtroGrid}>
        <div className={s.filtroPrincipal}>
          {pregunta ? (
            <>
              <div className={s.filtroEnunciado}>
                <h2 id="t-filtro" ref={titulo} tabIndex={-1} className={s.filtroPregunta}>
                  {pregunta.pregunta}
                </h2>
                {ayuda ? <p id={idAyuda} className={s.ayuda}>{ayuda}</p> : null}
              </div>

              <fieldset className={s.siNoGrande} aria-describedby={ayuda ? idAyuda : undefined}>
                <legend className="sr-only">{pregunta.pregunta}</legend>
                {OPCIONES.map((o) => (
                  <label key={String(o.valor)} className={s.botonSiNo} data-valor={o.valor ? "si" : "no"}>
                    <input
                      type="radio"
                      name={`filtro-${pregunta.codigo}`}
                      checked={resp[pregunta.codigo] === o.valor}
                      onChange={() => responder(pregunta.codigo, o.valor)}
                    />
                    <span className={s.botonSiNoTexto}>{o.etiqueta}</span>
                    <kbd className={s.atajo} aria-hidden="true">{o.tecla}</kbd>
                  </label>
                ))}
              </fieldset>

              <div className={s.filtroAcciones}>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPaso((p) => p - 1)} disabled={paso === 0}>
                  <Icon name="flecha" style={{ transform: "rotate(180deg)" }} />
                  Anterior
                </button>
                {resp[pregunta.codigo] !== undefined ? (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPaso((p) => p + 1)}>
                    Siguiente
                    <Icon name="flecha" />
                  </button>
                ) : null}
                <span className={s.atajos} aria-hidden="true">
                  Atajos: <kbd>S</kbd> sí, <kbd>N</kbd> no.
                </span>
              </div>
            </>
          ) : (
            <>
              <div className={s.filtroEnunciado}>
                <h2 id="t-filtro" ref={titulo} tabIndex={-1} className={s.filtroPregunta}>
                  {resp[PREGUNTA_RAIZ] === false ? "Tu organización no utiliza IA" : "Revisa tus respuestas"}
                </h2>
                <p className={s.ayuda}>
                  {resp[PREGUNTA_RAIZ] === false
                    ? "Con esta respuesta no hay más preguntas por ahora. Si en el futuro incorporan IA, conviene repetir el autodiagnóstico."
                    : "Con estas respuestas armamos un cuestionario a la medida de tu organización. Puedes cambiar cualquiera antes de continuar."}
                </p>
              </div>

              {yaHabiaRespuestas ? (
                <p className="callout" role="note">
                  <Icon name="info" />
                  <span>
                    Ya respondiste {nPreguntas(progreso?.controles_respondidos ?? 0)}. Si cambias estas respuestas, algunas
                    preguntas podrían dejar de aplicar y sus respuestas no contarán en tu resultado.
                  </span>
                </p>
              ) : null}

              {error ? <AvisoError error={error} onReintentar={confirmar} /> : null}

              <div className={s.filtroAcciones}>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPaso(total - 1)}>
                  <Icon name="flecha" style={{ transform: "rotate(180deg)" }} />
                  Anterior
                </button>
                <button type="button" className="btn btn-primary" onClick={confirmar} disabled={enviando} aria-busy={enviando}>
                  {enviando ? "Guardando…" : estimado === 0 ? "Confirmar" : "Comenzar el cuestionario"}
                  {!enviando ? <Icon name="flecha" /> : null}
                </button>
              </div>
            </>
          )}
        </div>

        <aside className={s.filtroResumen} aria-label="Tus respuestas">
          <p className={s.filtroResumenTitulo}>Tus respuestas</p>
          {preguntas.some((p) => resp[p.codigo] !== undefined) ? (
            <ol className={s.respondidas}>
              {preguntas.map((p, i) =>
                resp[p.codigo] === undefined ? null : (
                  <li key={p.codigo}>
                    <button
                      type="button"
                      className={s.respondida}
                      aria-current={i === paso ? "step" : undefined}
                      onClick={() => setPaso(i)}
                      aria-label={`Cambiar respuesta (${resp[p.codigo] ? "Sí" : "No"}): ${p.pregunta}`}
                    >
                      <span className={s.respondidaTexto}>{p.pregunta}</span>
                      <span className={s.respondidaValor} data-valor={resp[p.codigo] ? "si" : "no"}>
                        {resp[p.codigo] ? "Sí" : "No"}
                      </span>
                    </button>
                  </li>
                ),
              )}
            </ol>
          ) : (
            <p className={s.ayuda}>Tus respuestas aparecerán aquí; puedes volver a cualquiera con un clic.</p>
          )}
        </aside>
      </div>
    </section>
  );
}
