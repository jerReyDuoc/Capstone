"use client";

/**
 * Auditoría UX 16-11 · Fase 3: botón que, cuando está desactivado, dice POR QUÉ.
 *
 * - Desactivado = aria-disabled="true" (sigue siendo enfocable y el lector de pantalla lee el
 *   motivo vía aria-describedby); el clic se ignora.
 * - El motivo se ve como texto corto debajo del botón, no solo como tooltip.
 * - El aspecto (gris, sin marca, cursor not-allowed, sin hover) lo da globals.css en
 *   .btn[aria-disabled="true"].
 */
import { useId, type ButtonHTMLAttributes, type MouseEvent, type ReactNode } from "react";
import { Icon } from "./Icon";

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "disabled"> {
  /** Texto corto que explica qué falta. Si es null/"" el botón está activo. */
  motivo?: string | null;
  /** Desactivado sin motivo visible (p. ej. mientras se guarda: el propio botón dice "Guardando…"). */
  ocupado?: boolean;
  alinear?: "inicio" | "fin";
  children: ReactNode;
}

export function BotonConMotivo({ motivo, ocupado = false, alinear = "inicio", className = "btn btn-primary", onClick, children, type = "button", ...resto }: Props) {
  const idMotivo = useId();
  const desactivado = Boolean(motivo) || ocupado;
  const describedBy = [resto["aria-describedby"], motivo ? idMotivo : null].filter(Boolean).join(" ") || undefined;

  const alHacerClic = (e: MouseEvent<HTMLButtonElement>) => {
    if (desactivado) {
      e.preventDefault();
      return;
    }
    onClick?.(e);
  };

  const boton = (
    <button
      {...resto}
      type={desactivado && type === "submit" ? "button" : type}
      className={className}
      aria-disabled={desactivado || undefined}
      aria-describedby={describedBy}
      onClick={alHacerClic}
    >
      {children}
    </button>
  );

  if (!motivo) return boton;
  return (
    <span className="boton-con-motivo" data-alinear={alinear}>
      {boton}
      <span className="motivo-desactivado" id={idMotivo}>
        <Icon name="info" aria-hidden="true" />
        <span>{motivo}</span>
      </span>
    </span>
  );
}
