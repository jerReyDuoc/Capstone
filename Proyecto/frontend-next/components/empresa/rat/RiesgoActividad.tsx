"use client";

/**
 * Nivel de riesgo de una actividad del registro, explicado: probabilidad × impacto, qué lo sube (cada
 * factor con su detalle y qué hacer) y, si corresponde, por qué se recomienda una evaluación de impacto
 * con el acceso directo para generarla ya pre-llenada con esta actividad.
 */
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { TONO_RIESGO, type RiesgoActividad } from "@/lib/registroActividades";
import s from "./rat.module.css";

export function RiesgoDeActividad({ actividadId, riesgo }: { actividadId: number; riesgo: RiesgoActividad | null | undefined }) {
  if (!riesgo) {
    return (
      <section className={`card ${s.riesgo}`} aria-labelledby="titulo-riesgo">
        <h3 id="titulo-riesgo" className="card-title">Nivel de riesgo</h3>
        <p className="card-sub">Lo calculamos apenas elijas del mapa los sistemas o flujos que usa la actividad.</p>
      </section>
    );
  }
  const factores = riesgo.factores ?? [];
  return (
    <section className={`card ${s.riesgo}`} aria-labelledby="titulo-riesgo">
      <div className={s.cabezaFila}>
        <h3 id="titulo-riesgo" className="card-title">Nivel de riesgo</h3>
        <span className={`badge ${TONO_RIESGO[riesgo.nivel]}`}>
          {riesgo.nivel} · {riesgo.puntaje} de 25
        </span>
      </div>
      <p className="card-sub">
        Probabilidad {riesgo.probabilidad} ({(riesgo.probabilidad_nombre ?? "").toLocaleLowerCase("es")}) × impacto{" "}
        {riesgo.impacto} ({(riesgo.impacto_nombre ?? "").toLocaleLowerCase("es")}). Es una valoración orientativa calculada
        con lo que registraste.
      </p>

      {riesgo.requiere_pia ? (
        <div className="callout callout-aviso" role="status">
          <Icon name="escudo" />
          <div style={{ display: "grid", gap: 6 }}>
            <strong>Te recomendamos una evaluación de impacto para esta actividad</strong>
            <ul className={s.motivos}>
              {riesgo.motivos_pia.map((m) => <li key={m}>{m}</li>)}
            </ul>
            <span>
              <Link href={`/empresa/borradores?plantilla=pia&actividad=${actividadId}`}>
                Generar la evaluación de impacto con esta actividad
              </Link>
            </span>
          </div>
        </div>
      ) : null}

      {factores.length ? (
        <ul className={s.factores} aria-label="Qué sube el riesgo">
          {factores.map((f) => (
            <li key={f.titulo}>
              <span className={s.factorEje}>{f.eje === "impacto" ? "Impacto" : "Probabilidad"} +{f.puntos}</span>
              <strong>{f.titulo}</strong>
              <span>{f.detalle}</span>
              <span className={s.factorQue}><Icon name="chispa" />{f.tratamiento}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="card-sub">No encontramos factores que suban el riesgo de esta actividad.</p>
      )}
    </section>
  );
}
