"use client";

/**
 * Auditoría UX 16-11 · Fase 5.D: "Actualizado hace X" discreto + ícono para forzar la recarga.
 */
import { useEffect, useState } from "react";
import { haceTexto } from "@/lib/fechas";
import type { Actualizacion } from "@/hooks/useActualizacionAutomatica";
import { Icon } from "./Icon";

export function Actualizado({ estado, className = "" }: { estado: Actualizacion; className?: string }) {
  const { ultima, actualizando, actualizar } = estado;
  const [, setTic] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTic((n) => n + 1), 30_000);
    return () => clearInterval(t);
  }, []);

  return (
    <span className={`actualizado ${className}`}>
      <span aria-live="polite">{actualizando ? "Actualizando…" : ultima ? `Actualizado ${haceTexto(ultima)}` : ""}</span>
      <button
        type="button"
        className="icon-btn actualizado-boton"
        onClick={() => void actualizar()}
        aria-label="Volver a cargar los datos"
        title="Volver a cargar los datos"
        aria-busy={actualizando || undefined}
      >
        <Icon name="refrescar" className={actualizando ? "girando" : undefined} />
      </button>
    </span>
  );
}
