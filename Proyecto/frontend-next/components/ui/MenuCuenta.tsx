"use client";

/**
 * Auditoría UX 16-11 · Fase 4.A / 7: menú de cuenta en el extremo derecho del encabezado.
 * Reúne los datos de la cuenta y "Cerrar sesión" (que ya no ocupa lugar en la barra).
 *
 * Teclado: Enter/Espacio o ↓ abren y enfocan la primera opción; ↑/↓ recorren; Esc cierra y
 * devuelve el foco al botón; Tab fuera del menú lo cierra.
 */
import Link from "next/link";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export type OpcionCuenta =
  | { tipo: "enlace"; texto: string; href: string; icono?: IconName }
  | { tipo: "accion"; texto: string; onSelect: () => void | Promise<void>; icono?: IconName };

export function MenuCuenta({
  titulo,
  detalle,
  opciones,
  etiqueta = "Mi cuenta",
}: {
  /** Nombre visible (persona o rol). */
  titulo: string;
  /** Segunda línea opcional (correo, empresa). */
  detalle?: ReactNode;
  opciones: OpcionCuenta[];
  etiqueta?: string;
}) {
  const [abierto, setAbierto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const idMenu = useId();

  const items = () => [...(raiz.current?.querySelectorAll<HTMLElement>("[role='menuitem']") ?? [])];
  const enfocar = (i: number) => {
    const lista = items();
    lista[(i + lista.length) % lista.length]?.focus();
  };

  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => {
      if (!raiz.current?.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", fuera);
    return () => document.removeEventListener("mousedown", fuera);
  }, [abierto]);

  const cerrar = (devolverFoco = true) => {
    setAbierto(false);
    if (devolverFoco) boton.current?.focus();
  };

  const alTeclearBoton = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setAbierto(true);
      requestAnimationFrame(() => enfocar(0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setAbierto(true);
      requestAnimationFrame(() => enfocar(-1));
    }
  };

  const alTeclearMenu = (e: KeyboardEvent) => {
    const lista = items();
    const i = lista.indexOf(document.activeElement as HTMLElement);
    if (e.key === "Escape") {
      e.preventDefault();
      cerrar();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      enfocar(i + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      enfocar(i - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      enfocar(0);
    } else if (e.key === "End") {
      e.preventDefault();
      enfocar(-1);
    } else if (e.key === "Tab") {
      cerrar(false);
    }
  };

  return (
    <div className="menu-cuenta" ref={raiz}>
      <button
        ref={boton}
        type="button"
        className="menu-cuenta-boton"
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-controls={idMenu}
        onClick={() => setAbierto((x) => !x)}
        onKeyDown={alTeclearBoton}
      >
        <span className="menu-cuenta-avatar" aria-hidden="true">
          <Icon name="usuario" />
        </span>
        <span className="menu-cuenta-texto">{etiqueta}</span>
        <Icon name="chevron" className="menu-cuenta-chevron" aria-hidden="true" />
      </button>
      {abierto ? (
        <div className="menu-cuenta-panel" id={idMenu} role="menu" aria-label={etiqueta} onKeyDown={alTeclearMenu}>
          <div className="menu-cuenta-datos" role="presentation">
            <strong>{titulo}</strong>
            {detalle ? <span>{detalle}</span> : null}
          </div>
          {opciones.map((o) =>
            o.tipo === "enlace" ? (
              <Link key={o.texto} href={o.href} role="menuitem" className="menu-cuenta-item" tabIndex={-1} onClick={() => cerrar(false)}>
                {o.icono ? <Icon name={o.icono} /> : null}
                {o.texto}
              </Link>
            ) : (
              <button
                key={o.texto}
                type="button"
                role="menuitem"
                className="menu-cuenta-item"
                tabIndex={-1}
                onClick={() => {
                  cerrar(false);
                  void o.onSelect();
                }}
              >
                {o.icono ? <Icon name={o.icono} /> : null}
                {o.texto}
              </button>
            ),
          )}
        </div>
      ) : null}
    </div>
  );
}
