"use client";

/**
 * Auditoría UX 16-11 · Fase 9.1: campo de archivo propio, igual en todo el producto.
 *
 *  - Botón con estilo + nombre del archivo elegido con corte elegante (…) y opción de quitarlo.
 *  - Arrastrar y soltar en escritorio.
 *  - Todo en español: no depende del idioma del navegador ("No se eligió ningún archivo").
 *  - Estado de error (aria-invalid + mensaje conectado con aria-describedby).
 *
 * El <input type="file"> nativo sigue existiendo (accesible y enfocable), solo se oculta a la vista.
 */
import { forwardRef, useId, useState, type DragEvent } from "react";
import { Icon } from "./Icon";

interface Props {
  id?: string;
  accept?: string;
  archivo: File | null;
  onCambiar: (archivo: File | null) => void;
  /** Mensaje de error a la vista (o null). */
  error?: string | null;
  /** id(s) de la ayuda del campo, para aria-describedby. */
  describedBy?: string;
  disabled?: boolean;
  textoBoton?: string;
}

export const CampoArchivo = forwardRef<HTMLInputElement, Props>(function CampoArchivo(
  { id, accept, archivo, onCambiar, error, describedBy, disabled = false, textoBoton = "Elegir archivo" },
  ref,
) {
  const propio = useId();
  const idInput = id ?? propio;
  const idError = `${idInput}-error`;
  const idNombre = `${idInput}-nombre`;
  const [encima, setEncima] = useState(false);

  const soltar = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setEncima(false);
    if (disabled) return;
    const f = e.dataTransfer.files?.[0];
    if (f) onCambiar(f);
  };

  return (
    <div className="campo-archivo-raiz">
      <div
        className="campo-archivo"
        data-encima={encima || undefined}
        data-error={error ? true : undefined}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setEncima(true);
        }}
        onDragLeave={() => setEncima(false)}
        onDrop={soltar}
      >
        <input
          ref={ref}
          id={idInput}
          type="file"
          className="campo-archivo-input"
          accept={accept}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={[idNombre, describedBy, error ? idError : null].filter(Boolean).join(" ")}
          onChange={(e) => onCambiar(e.target.files?.[0] ?? null)}
        />
        <label htmlFor={idInput} className="btn btn-ghost btn-sm campo-archivo-boton">
          <Icon name="subir" aria-hidden="true" />
          {archivo ? "Cambiar archivo" : textoBoton}
        </label>
        <span className="campo-archivo-nombre" id={idNombre} title={archivo?.name}>
          {archivo ? archivo.name : <span className="campo-archivo-vacio">Ningún archivo elegido · también puedes arrastrarlo aquí</span>}
        </span>
        {archivo ? (
          <button
            type="button"
            className="icon-btn campo-archivo-quitar"
            onClick={() => onCambiar(null)}
            aria-label={`Quitar el archivo ${archivo.name}`}
            disabled={disabled}
          >
            <Icon name="cerrar" />
          </button>
        ) : null}
      </div>
      {error ? (
        <p className="dialogo-error" id={idError} role="alert">
          <Icon name="alerta" aria-hidden="true" />
          {error}
        </p>
      ) : null}
    </div>
  );
});
