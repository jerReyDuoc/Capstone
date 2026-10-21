"use client";

import Link from "next/link";
import { usePanel } from "@/hooks/usePanel";
import type { BrechaVista } from "@/lib/types";
import { BadgeCriticidad, BadgeEstado } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";

/** Las N brechas más urgentes (ya vienen ordenadas por criticidad y estado). */
export function ResumenBrechas({ brechas, limite = 4 }: { brechas: BrechaVista[]; limite?: number }) {
  const { href } = usePanel();
  const top = brechas.slice(0, limite);

  return (
    <section className="card" aria-labelledby="resumen-brechas-titulo" style={{ display: "grid", gap: 16, alignContent: "start" }}>
      <div className="card-head" style={{ marginBottom: 0 }}>
        <div>
          <h2 className="card-title" id="resumen-brechas-titulo">Resumen de brechas</h2>
          <p className="card-sub">
            {brechas.length === 0
              ? "Sin brechas abiertas"
              : `Las ${top.length} más urgentes de ${brechas.length} abiertas`}
          </p>
        </div>
      </div>

      {top.length === 0 ? (
        <p className="card-sub">No se detectaron controles incumplidos. Mantén la evidencia actualizada para conservar el nivel.</p>
      ) : (
        <ol className="gap-list">
          {top.map((b) => (
            <li key={b.respuestaId} className="gap-item">
              <div className="gap-top">
                <BadgeCriticidad criticidad={b.criticidad} />
                <BadgeEstado estado={b.estado} />
                <span className="code">{b.codigo}</span>
              </div>
              <p>{b.descripcion}</p>
              <p className="gap-meta">
                {b.dominio}
                {b.rutaFormativa ? ` · Ruta: ${b.rutaFormativa}` : ""}
              </p>
            </li>
          ))}
        </ol>
      )}

      {brechas.length > 0 ? (
        <Link href={href("/panel/brechas")} className="btn btn-ghost" style={{ justifySelf: "start" }}>
          Ver todas las brechas
          <Icon name="flecha" />
        </Link>
      ) : null}
    </section>
  );
}
