"use client";

/**
 * HU-01 / HU-02 · Cuestionario adaptativo del encuestado (se monta en /encuesta).
 *
 *   preguntas iniciales F1–F7 → controles aplicables (uno por uno) → revisión → completar
 *                                                                        ↓
 *                                                  /panel?evaluacion=ID (resultados)
 */
import Link from "next/link";
import { AvisoError } from "@/components/inicio/AvisoError";
import { Icon } from "@/components/ui/Icon";
import { useCuestionario } from "@/hooks/useCuestionario";
import { IndiceControles } from "./IndiceControles";
import { PasoControl } from "./PasoControl";
import { PasoFiltro } from "./PasoFiltro";
import { RevisionFinal } from "./RevisionFinal";
import s from "./cuestionario.module.css";

export function Cuestionario({ evaluacionId, onLimites }: { evaluacionId: number; onLimites: () => void }) {
  const c = useCuestionario(evaluacionId);
  const { fase, progreso } = c;

  if (fase.tipo === "cargando") {
    return <div className="skeleton" style={{ height: 420 }} role="status" aria-label="Cargando el cuestionario" />;
  }

  if (fase.tipo === "error") {
    return <AvisoError error={fase.error} onReintentar={() => void c.recargar()} />;
  }

  if (fase.tipo === "cerrada") {
    return (
      <section className={`card ${s.cierre}`} aria-labelledby="t-cerrada">
        <Icon name="check" />
        <h2 id="t-cerrada" className={s.textoPregunta}>Tu evaluación está completada</h2>
        <p>Ya calculamos tu nivel de madurez y las brechas priorizadas. Las respuestas quedaron cerradas y no se pueden editar.</p>
        <Link href={`/panel?evaluacion=${evaluacionId}`} className="btn btn-primary" prefetch={false}>
          Ver mis resultados
          <Icon name="flecha" />
        </Link>
      </section>
    );
  }

  if (fase.tipo === "filtro") {
    return (
      <div className={s.columna}>
        <PasoFiltro c={c} />
      </div>
    );
  }

  // F1 = NO: ningún control aplica, solo queda confirmar
  if (c.controles.length === 0) {
    return (
      <div className={s.columna}>
        <RevisionFinal evaluacionId={evaluacionId} c={c} />
      </div>
    );
  }

  const pct = Math.round(progreso?.porcentaje ?? 0);
  const control = c.controles[c.indice];

  return (
    <div className={s.layout}>
      <IndiceControles c={c} />
      <div className={s.columna}>
        <div className={s.avance}>
          <div className={s.avanceFila}>
            <span>
              <strong>{progreso?.controles_respondidos ?? 0}</strong> de <strong>{progreso?.controles_aplicables ?? 0}</strong> controles respondidos
            </span>
            <span>
              <strong>{pct} %</strong>
            </span>
          </div>
          <div className="meter" role="progressbar" aria-label="Avance del cuestionario" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
            <span style={{ width: `${pct}%` }} />
          </div>
        </div>

        {fase.tipo === "revision" || !control ? (
          <RevisionFinal evaluacionId={evaluacionId} c={c} />
        ) : (
          <>
            <PasoControl key={control.id_control} c={c} control={control} onLimites={onLimites} />
            {progreso && progreso.controles_pendientes === 0 ? (
              <div className="callout" role="note">
                <Icon name="check" />
                <span>
                  Respondiste todos los controles.{" "}
                  <button type="button" className="link-btn" onClick={c.irARevision}>
                    Ir a la revisión final
                  </button>
                </span>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
