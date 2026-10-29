"use client";

/**
 * Correcciones 29-10 · Botón (i) que muestra un detalle secundario sin ocupar espacio.
 *
 * Se abre con clic, toque o teclado (Enter/Espacio) y se cierra con Escape o al hacer clic
 * fuera; el hover solo no sirve en pantallas táctiles ni con teclado (WCAG 2.1.1 y 1.4.13).
 */
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Icon } from "./Icon";

export function InfoTip({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLSpanElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const id = useId();

  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: PointerEvent) => {
      if (caja.current && !caja.current.contains(e.target as Node)) setAbierto(false);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAbierto(false);
        boton.current?.focus();
      }
    };
    document.addEventListener("pointerdown", fuera);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("pointerdown", fuera);
      document.removeEventListener("keydown", tecla);
    };
  }, [abierto]);

  return (
    <span className="infotip" ref={caja}>
      <button
        ref={boton}
        type="button"
        className="infotip-boton"
        aria-expanded={abierto}
        aria-controls={id}
        aria-label={etiqueta}
        onClick={() => setAbierto((v) => !v)}
      >
        <Icon name="info" />
      </button>
      {/* Siempre en el DOM (oculto) para que aria-controls apunte a algo que existe */}
      <span id={id} className="infotip-panel" role="note" hidden={!abierto}>
        {children}
      </span>
    </span>
  );
}
