"use client";

/**
 * HU-01 · Revisión final y cierre definitivo (POST /completar).
 *
 * Antes de habilitar "Completar" se verifica en el navegador lo mismo que exige el backend
 * (CompletarEvaluacionUseCase): todos los controles respondidos, ninguna evidencia en
 * validación y cada "Requiere revisión" con al menos una evidencia. El backend lo vuelve a
 * comprobar; si algo cambió entre medio, su error se muestra con <AvisoError>.
 *
 * Al completar se va al panel de resultados (/panel?evaluacion=ID), que para el encuestado
 * se carga vía BFF (ver hooks/usePanel.tsx).
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AvisoError } from "@/components/inicio/AvisoError";
import { Icon } from "@/components/ui/Icon";
import type { Cuestionario } from "@/hooks/useCuestionario";
import {
  bloqueosParaCompletar,
  ESTADO_POR_VALOR,
  esEstadoDeclarado,
  evidenciaEnCurso,
  type Bloqueo,
  type EvidenciaApi,
} from "@/lib/cuestionario/modelo";
import { comoErrorEncuesta } from "@/lib/encuesta/cliente";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";
import s from "./cuestionario.module.css";

const TEXTO_BLOQUEO: Record<Bloqueo["tipo"], string> = {
  pendiente: "Sin responder",
  "revision-sin-evidencia": "Requiere revisión sin evidencia",
  "evidencia-en-curso": "Evidencia en validación",
};

/** Ejecuta las promesas de a `n` para no saturar el BFF con 40 consultas juntas. */
async function enLotes<T, R>(items: T[], n: number, f: (x: T) => Promise<R>): Promise<R[]> {
  const out: R[] = [];
  for (let i = 0; i < items.length; i += n) out.push(...(await Promise.all(items.slice(i, i + n).map(f))));
  return out;
}

export function RevisionFinal({ evaluacionId, c }: { evaluacionId: number; c: Cuestionario }) {
  const router = useRouter();
  const { progreso, obtenerDetalle, refrescarProgreso } = c;
  const [evidencias, setEvidencias] = useState<Map<number, EvidenciaApi[]> | null>(null);
  const [confirmado, setConfirmado] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<ErrorEncuesta | null>(null);
  const [completadaSinControles, setCompletadaSinControles] = useState(false);
  const titulo = useRef<HTMLHeadingElement>(null);

  useEffect(() => titulo.current?.focus(), []);

  /** Respuestas que pueden tener evidencia (las demás no la admiten). */
  const candidatas = (progreso?.respondidos ?? []).filter((r) =>
    esEstadoDeclarado(r.estado_clasificacion) ? ESTADO_POR_VALOR[r.estado_clasificacion].admiteEvidencia : false,
  );
  // Clave estable: refrescar el progreso no vuelve a pedir todas las evidencias
  const claveCandidatas = candidatas.map((r) => r.id_respuesta).join(",");
  const conEvidencia = useMemo(() => candidatas, [claveCandidatas]); // eslint-disable-line react-hooks/exhaustive-deps

  const cargarEvidencias = useCallback(
    async (soloIds?: number[]) => {
      const objetivo = soloIds ? conEvidencia.filter((r) => soloIds.includes(r.id_respuesta)) : conEvidencia;
      const detalles = await enLotes(objetivo, 4, (r) => obtenerDetalle(r.id_respuesta, true).catch(() => null));
      setEvidencias((prev) => {
        const m = new Map(prev ?? []);
        objetivo.forEach((r, i) => m.set(r.id_respuesta, detalles[i]?.evidencias ?? m.get(r.id_respuesta) ?? []));
        return m;
      });
    },
    [conEvidencia, obtenerDetalle],
  );

  useEffect(() => {
    void cargarEvidencias();
  }, [cargarEvidencias]);

  // Mientras haya evidencias validándose, se vuelve a consultar solo esas
  const idsEnCurso = useMemo(
    () => [...(evidencias ?? new Map<number, EvidenciaApi[]>()).entries()].filter(([, ev]) => ev.some(evidenciaEnCurso)).map(([id]) => id),
    [evidencias],
  );
  useEffect(() => {
    if (!idsEnCurso.length) return;
    const t = window.setTimeout(async () => {
      await cargarEvidencias(idsEnCurso);
      await refrescarProgreso().catch(() => undefined); // la IA puede cambiar el estado final
    }, 4000);
    return () => window.clearTimeout(t);
  }, [idsEnCurso, cargarEvidencias, refrescarProgreso]);

  if (!progreso) return null;
  const sinControles = progreso.controles_aplicables === 0;
  const bloqueos = evidencias ? bloqueosParaCompletar(progreso, evidencias) : [];
  const verificando = evidencias === null;
  const puedeCompletar = !verificando && bloqueos.length === 0 && confirmado && !enviando;

  async function completar() {
    setEnviando(true);
    setError(null);
    try {
      await c.completar();
      if (sinControles) {
        setCompletadaSinControles(true);
        setEnviando(false);
        return;
      }
      router.push(`/panel?evaluacion=${evaluacionId}`);
    } catch (e) {
      setError(comoErrorEncuesta(e));
      setEnviando(false);
      await c.refrescarProgreso().catch(() => undefined);
    }
  }

  if (completadaSinControles) {
    return (
      <section className={`card ${s.cierre}`} aria-labelledby="t-fin">
        <Icon name="check" />
        <h2 id="t-fin" ref={titulo} tabIndex={-1} className={s.textoPregunta}>Autodiagnóstico registrado</h2>
        <p>Como tu organización hoy no utiliza IA, no hay controles que evaluar ni brechas que cerrar. Si eso cambia, vuelve a hacer el autodiagnóstico.</p>
      </section>
    );
  }

  return (
    <section className={`card ${s.pregunta}`} aria-labelledby="t-revision">
      <div style={{ display: "grid", gap: 8 }}>
        <span className="eyebrow" style={{ margin: 0 }}>Último paso</span>
        <h2 id="t-revision" ref={titulo} tabIndex={-1} className={s.textoPregunta}>
          {sinControles ? "Confirma tu autodiagnóstico" : "Revisa y completa tu evaluación"}
        </h2>
        <p className={s.ayuda}>
          {sinControles
            ? "Indicaste que tu organización no utiliza IA, así que ningún control aplica."
            : "Al completarla calculamos tu nivel de madurez por dominio y las brechas priorizadas. Después ya no podrás modificar las respuestas."}
        </p>
      </div>

      {!sinControles ? (
        <div className={s.dimensiones}>
          {progreso.por_dimension.map((d) => (
            <div key={d.dominio_id ?? "x"} className={s.dimension}>
              <div className={s.dimensionFila}>
                <span>{d.dominio ?? "Sin dominio"}</span>
                <span>
                  {d.respondidos}/{d.aplicables}
                </span>
              </div>
              <div className="meter" role="progressbar" aria-label={`Avance en ${d.dominio}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(d.porcentaje)}>
                <span style={{ width: `${d.porcentaje}%` }} />
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {verificando && conEvidencia.length ? (
        <p className={s.ayuda} role="status">Revisando el estado de tus evidencias…</p>
      ) : null}

      {bloqueos.length ? (
        <div style={{ display: "grid", gap: 12 }}>
          <p className={s.campoEtiqueta}>Antes de completar, resuelve esto:</p>
          <ul className={s.bloqueos}>
            {bloqueos.map((b) => {
              const i = c.controles.findIndex((x) => x.id_control === b.idControl);
              return (
                <li key={`${b.tipo}-${b.idControl}`} className={s.bloqueo}>
                  <span>
                    <strong style={{ fontFamily: "var(--font-mono)" }}>{b.codigo}</strong> · {TEXTO_BLOQUEO[b.tipo]}
                  </span>
                  {b.tipo === "evidencia-en-curso" ? (
                    <span className="badge tone-info">Esperando a la IA</span>
                  ) : i >= 0 ? (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => c.irA(i)}>
                      Ir al control
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {!verificando && !bloqueos.length ? (
        <label className={s.check}>
          <input type="checkbox" checked={confirmado} onChange={(e) => setConfirmado(e.target.checked)} />
          <span>Revisé mis respuestas y entiendo que, al completar, la evaluación queda cerrada y no se puede editar.</span>
        </label>
      ) : null}

      {error ? <AvisoError error={error} onReintentar={completar} /> : null}

      <div className={s.acciones}>
        {!sinControles ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => c.irA(0)}>
            <Icon name="flecha" style={{ transform: "rotate(180deg)" }} />
            Volver a las respuestas
          </button>
        ) : (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => void c.editarFiltro()}>
            Cambiar preguntas iniciales
          </button>
        )}
        <button type="button" className="btn btn-primary" onClick={completar} disabled={!puedeCompletar} aria-busy={enviando}>
          {enviando ? "Calculando resultados…" : sinControles ? "Completar" : "Completar y ver resultados"}
          {!enviando ? <Icon name="flecha" /> : null}
        </button>
      </div>
    </section>
  );
}
