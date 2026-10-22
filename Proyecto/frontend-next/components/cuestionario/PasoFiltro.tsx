"use client";

/**
 * HU-01 · Preguntas iniciales F1–F7. Se responden de a una y adaptan el cuestionario:
 *   - F1 = NO  → la organización no usa IA: ningún control aplica y el resto no se pregunta.
 *   - F2..F7 = SÍ suman controles específicos (datos sensibles, terceros, LLM, agentes…).
 * Al final se muestra el resumen y se guarda todo junto (el backend exige las 7).
 */
import { useEffect, useId, useRef, useState } from "react";
import { AvisoError } from "@/components/inicio/AvisoError";
import { Icon } from "@/components/ui/Icon";
import type { Cuestionario } from "@/hooks/useCuestionario";
import {
  CONTROLES_POR_FILTRO,
  controlesEstimados,
  cuerpoFiltro,
  PREGUNTA_RAIZ,
  preguntasVisibles,
} from "@/lib/cuestionario/modelo";
import { comoErrorEncuesta } from "@/lib/encuesta/cliente";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";
import s from "./cuestionario.module.css";

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

  if (!filtro) return null;
  const total = preguntas.length;
  const enResumen = paso >= total;
  const pregunta = enResumen ? null : preguntas[paso];
  const estimado = controlesEstimados(resp);
  const yaHabiaRespuestas = (progreso?.controles_respondidos ?? 0) > 0;

  function responder(codigo: string, valor: boolean) {
    const nuevas = { ...resp, [codigo]: valor };
    setRespuestasFiltro(nuevas);
    setError(null);
    // Pequeña pausa para que se vea la selección antes de pasar a la siguiente
    window.setTimeout(() => {
      const visibles = preguntasVisibles(filtro!.preguntas, nuevas);
      const actual = visibles.findIndex((p) => p.codigo === codigo);
      setPaso(actual + 1);
    }, 180);
  }

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
      <div className={s.avance}>
        <div className={s.avanceFila}>
          <span className="eyebrow" style={{ margin: 0 }}>Contexto de tu organización</span>
          <span>
            {enResumen ? "Revisión" : (
              <>Pregunta <strong>{paso + 1}</strong> de <strong>{total}</strong></>
            )}
          </span>
        </div>
        <div className="meter" role="progressbar" aria-label="Avance de las preguntas iniciales" aria-valuemin={0} aria-valuemax={total} aria-valuenow={Math.min(paso, total)}>
          <span style={{ width: `${(Math.min(paso, total) / Math.max(total, 1)) * 100}%` }} />
        </div>
      </div>

      {pregunta ? (
        <>
          <div style={{ display: "grid", gap: 8 }}>
            <h2 id="t-filtro" ref={titulo} tabIndex={-1} className={s.textoPregunta}>
              {pregunta.pregunta}
            </h2>
            {pregunta.descripcion ? (
              <p id={idAyuda} className={s.ayuda}>{pregunta.descripcion}</p>
            ) : null}
          </div>

          <fieldset className={`${s.opciones} ${s.siNo}`} aria-describedby={pregunta.descripcion ? idAyuda : undefined}>
            <legend className="sr-only">{pregunta.pregunta}</legend>
            {[
              { valor: true, etiqueta: "Sí" },
              { valor: false, etiqueta: "No" },
            ].map((o) => (
              <label key={String(o.valor)} className={s.opcion}>
                <input
                  type="radio"
                  name={`filtro-${pregunta.codigo}`}
                  checked={resp[pregunta.codigo] === o.valor}
                  onChange={() => responder(pregunta.codigo, o.valor)}
                />
                <span className={s.opcionEtiqueta}>{o.etiqueta}</span>
              </label>
            ))}
          </fieldset>

          <Estimado codigo={pregunta.codigo} estimado={estimado} raizRespondida={resp[PREGUNTA_RAIZ] !== undefined} />

          <div className={s.acciones}>
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
          </div>
        </>
      ) : (
        <>
          <div style={{ display: "grid", gap: 8 }}>
            <h2 id="t-filtro" ref={titulo} tabIndex={-1} className={s.textoPregunta}>
              {resp[PREGUNTA_RAIZ] === false ? "Tu organización no utiliza IA" : "Revisa tus respuestas"}
            </h2>
            <p className={s.ayuda}>
              {resp[PREGUNTA_RAIZ] === false
                ? "Con esta respuesta ningún control de la matriz aplica todavía. Si en el futuro incorporan IA, conviene repetir el autodiagnóstico."
                : "Con estas respuestas armamos un cuestionario a la medida de tu organización. Puedes cambiar cualquiera antes de continuar."}
            </p>
          </div>

          <ul className={s.resumenFiltro}>
            {preguntas.map((p, i) => (
              <li key={p.codigo}>
                <span>
                  <strong>{resp[p.codigo] ? "Sí" : "No"}</strong> · {p.pregunta}
                </span>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setPaso(i)} aria-label={`Cambiar respuesta: ${p.pregunta}`}>
                  Cambiar
                </button>
              </li>
            ))}
          </ul>

          <div className={s.estimado} role="status">
            <span className={s.estimadoValor}>{estimado}</span>
            <span className={s.estimadoTexto}>
              {estimado === 0 ? "controles aplican a tu organización." : "controles de la matriz aplican a tu organización. Responderás uno por uno; tu avance se guarda solo."}
            </span>
          </div>

          {yaHabiaRespuestas ? (
            <p className="callout" role="note">
              <Icon name="info" />
              <span>
                Ya respondiste {progreso?.controles_respondidos} controles. Si cambias estas preguntas, las respuestas de los
                controles que dejen de aplicar no contarán en tu resultado.
              </span>
            </p>
          ) : null}

          {error ? <AvisoError error={error} onReintentar={confirmar} /> : null}

          <div className={s.acciones}>
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
    </section>
  );
}

function Estimado({ codigo, estimado, raizRespondida }: { codigo: string; estimado: number; raizRespondida: boolean }) {
  const suma = CONTROLES_POR_FILTRO[codigo];
  let texto: string;
  if (codigo === PREGUNTA_RAIZ) texto = "Si respondes No, ningún control aplica y el diagnóstico termina aquí.";
  else if (suma) texto = `Si respondes Sí, se suman ${suma} controles específicos a tu cuestionario.`;
  else texto = "";
  return (
    <div className={s.estimado} aria-live="polite">
      <span>
        <span className={s.estimadoValor}>{raizRespondida ? estimado : "—"}</span>{" "}
        <span className={s.estimadoTexto}>controles aplican hasta ahora</span>
      </span>
      {texto ? <span className={s.estimadoTexto}>{texto}</span> : null}
    </div>
  );
}
