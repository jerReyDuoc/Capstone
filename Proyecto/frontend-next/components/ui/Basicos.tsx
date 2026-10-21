"use client";

import type { ReactNode } from "react";
import { usePanel } from "@/hooks/usePanel";
import { CRITICIDAD_TONO, formatoPuntaje, NIVELES } from "@/lib/madurez";
import type { Criticidad, NivelMadurez } from "@/lib/types";
import { Icon, type IconName } from "./Icon";

export function BadgeNivel({ nivel }: { nivel: NivelMadurez }) {
  return <span className={`badge tone-${NIVELES[nivel].tono}`}>{NIVELES[nivel].etiqueta}</span>;
}

export function BadgeCriticidad({ criticidad }: { criticidad: Criticidad }) {
  return <span className={`badge tone-${CRITICIDAD_TONO[criticidad]}`}>{criticidad}</span>;
}

export function BadgeEstado({ estado }: { estado: "no_cumplido" | "parcialmente_cumplido" }) {
  return estado === "no_cumplido" ? (
    <span className="badge tone-alto">No cumplido</span>
  ) : (
    <span className="badge tone-medio">Parcial</span>
  );
}

export function Kpi({
  icono,
  etiqueta,
  valor,
  sufijo,
  pista,
  medidor,
  className = "",
}: {
  icono: IconName;
  etiqueta: string;
  valor: ReactNode;
  sufijo?: string;
  pista?: ReactNode;
  /** 0-100: dibuja la barra de progreso de la tarjeta. */
  medidor?: number;
  className?: string;
}) {
  return (
    <div className={`card kpi ${className}`} role="group" aria-label={etiqueta}>
      <p className="kpi-label">
        <Icon name={icono} />
        {etiqueta}
      </p>
      <p className="kpi-value">
        {valor}
        {sufijo ? <small>{sufijo}</small> : null}
      </p>
      {medidor != null ? (
        <div
          className="meter"
          role="meter"
          aria-label={`${etiqueta}: ${formatoPuntaje(medidor)} de 100`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(medidor)}
        >
          <span style={{ width: `${Math.max(0, Math.min(100, medidor))}%` }} />
        </div>
      ) : null}
      {pista ? <p className="kpi-hint">{pista}</p> : null}
    </div>
  );
}

/* ---------- Estados de carga / vacío / error ---------- */

export function Cargando() {
  return (
    <div role="status" aria-live="polite" className="grid">
      <span className="sr-only">Cargando el panel…</span>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="skeleton col-3 md-col-3" style={{ height: 132 }} />
      ))}
      <div className="skeleton col-7 md-col-7" style={{ height: 460 }} />
      <div className="skeleton col-5 md-col-5" style={{ height: 460 }} />
    </div>
  );
}

export function EstadoPanel({ children }: { children: (panel: import("@/lib/types").PanelVista) => ReactNode }) {
  const { estado, recargar } = usePanel();

  if (estado.tipo === "cargando") return <Cargando />;

  if (estado.tipo === "sin-evaluaciones")
    return (
      <div className="state" role="status">
        <Icon name="diagnostico" width={32} height={32} style={{ color: "var(--accent)" }} />
        <h2>Aún no hay evaluaciones</h2>
        <p>Cuando tu empresa complete el autodiagnóstico, aquí verás su nivel de madurez y las brechas priorizadas.</p>
      </div>
    );

  if (estado.tipo === "sin-resumen")
    return (
      <div className="state" role="status">
        <Icon name="info" width={32} height={32} style={{ color: "var(--medio)" }} />
        <h2>Esta evaluación todavía no tiene resultados</h2>
        <p>
          El resumen se genera al completar el cuestionario. Termina las preguntas pendientes o elige otra evaluación
          en el selector de arriba.
        </p>
      </div>
    );

  if (estado.tipo === "error")
    return (
      <div className="state" role="alert">
        <Icon name="brechas" width={32} height={32} style={{ color: "var(--alto)" }} />
        <h2>No pudimos cargar el panel</h2>
        <p>{estado.mensaje}</p>
        <button type="button" className="btn btn-primary" onClick={recargar}>
          <Icon name="refrescar" />
          Reintentar
        </button>
      </div>
    );

  return <>{children(estado.panel)}</>;
}
