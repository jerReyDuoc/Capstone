"use client";

import Link from "next/link";
import { usePanel } from "@/hooks/usePanel";
import type { BrechaVista } from "@/lib/types";
import { BadgeEstado, BadgeSeveridad } from "@/components/ui/Basicos";
import { Icon } from "@/components/ui/Icon";

/** Las N brechas más urgentes (ya vienen priorizadas por severidad, HU-11). */
export function ResumenBrechas({ brechas, limite = 4 }: { brechas: BrechaVista[]; limite?: number }) {
  const { href } = usePanel();
  const top = brechas.slice(0, limite);

  return (
    <section className="card pila-media" aria-labelledby="resumen-brechas-titulo">
      <div className="card-head card-head-sin-margen">
        <div>
          <h2 className="card-title" id="resumen-brechas-titulo">Brechas prioritarias</h2>
          <p className="card-sub">
            {brechas.length === 0
              ? "Sin brechas abiertas"
              : `Las ${top.length} más urgentes de ${brechas.length} abiertas`}
          </p>
        </div>
      </div>

      {top.length === 0 ? (
        <p className="card-sub">No se detectaron brechas. Mantén la evidencia actualizada para conservar el nivel.</p>
      ) : (
        <ol className="gap-list">
          {top.map((b) => (
            <li key={b.respuestaId} className="gap-item">
              <div className="gap-top">
                <span className="code gap-prioridad">#{b.prioridad}</span>
                <BadgeSeveridad severidad={b.severidad} />
                <BadgeEstado estado={b.estado} />
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
        <Link href={href("/panel/brechas")} className="btn btn-ghost alinear-inicio">
          Ver listado priorizado
          <Icon name="flecha" />
        </Link>
      ) : null}
    </section>
  );
}
