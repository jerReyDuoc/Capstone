"use client";

/**
 * Campo de contraseña con botón para mostrarla u ocultarla (ícono de ojo).
 *
 * Se usa en TODOS los formularios que piden una contraseña (ingreso de empresas y de
 * administradores, activación de cuenta y restablecimiento), así la lógica vive en un solo lugar.
 *
 * - El botón es type="button": nunca envía el formulario.
 * - aria-label cambia entre "Mostrar contraseña" y "Ocultar contraseña" y aria-controls apunta al
 *   campo. Funciona con teclado (Tab + Enter/Espacio) y con toque (área de 40 × 40 px).
 * - Al enviar el formulario la contraseña vuelve a ocultarse, para que no quede a la vista ni la
 *   guarde el navegador como texto.
 * - Recibe las mismas props que un <input> (id, value, onChange, autoComplete, aria-*, ref…).
 */
import { useEffect, useRef, useState, type ComponentPropsWithRef, type Ref } from "react";
import { Icon } from "./Icon";

/** Lo que cambia según el estado (lógica pura, probada en tests/mejoras_1911.test.ts). */
export function textosVisibilidad(visible: boolean) {
  return visible
    ? ({ type: "text", etiqueta: "Ocultar contraseña", icono: "ojoTachado" } as const)
    : ({ type: "password", etiqueta: "Mostrar contraseña", icono: "ojo" } as const);
}

type Props = Omit<ComponentPropsWithRef<"input">, "type"> & {
  /** Clase extra del contenedor (el input conserva su `className`). */
  claseContenedor?: string;
};

function asignarRef<T>(ref: Ref<T> | undefined, valor: T | null) {
  if (typeof ref === "function") ref(valor);
  else if (ref) (ref as { current: T | null }).current = valor;
}

export function PasswordInput({ claseContenedor = "", ref, id, disabled, ...props }: Props) {
  const [visible, setVisible] = useState(false);
  const campo = useRef<HTMLInputElement | null>(null);
  const t = textosVisibilidad(visible);

  // Al enviar el formulario se vuelve a ocultar
  useEffect(() => {
    const form = campo.current?.form;
    if (!form) return;
    const ocultar = () => setVisible(false);
    form.addEventListener("submit", ocultar);
    return () => form.removeEventListener("submit", ocultar);
  }, []);

  return (
    <span className={`campo-contrasena ${claseContenedor}`.trim()}>
      <input
        {...props}
        id={id}
        disabled={disabled}
        ref={(el) => {
          campo.current = el;
          asignarRef(ref, el);
        }}
        type={t.type}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
      />
      <button
        type="button"
        className="campo-contrasena-boton"
        aria-label={t.etiqueta}
        aria-controls={id}
        title={t.etiqueta}
        disabled={disabled}
        onClick={() => setVisible((v) => !v)}
      >
        <Icon name={t.icono} width={20} height={20} />
      </button>
    </span>
  );
}
