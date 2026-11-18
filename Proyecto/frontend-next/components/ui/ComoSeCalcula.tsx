/**
 * Auditoría UX 16-11 · Fase 5.D: toda explicación de metodología va en un desplegable cerrado
 * por defecto. <details>/<summary> nativo: accesible por teclado y lector de pantalla sin JS.
 */
import type { ReactNode } from "react";
import { Icon } from "./Icon";

export function ComoSeCalcula({
  titulo = "¿Cómo se calcula?",
  children,
  abierto = false,
  className = "",
}: {
  titulo?: string;
  children: ReactNode;
  abierto?: boolean;
  className?: string;
}) {
  return (
    <details className={`como-se-calcula ${className}`} open={abierto || undefined}>
      <summary>
        <Icon name="info" aria-hidden="true" />
        <span>{titulo}</span>
        <Icon name="chevron" className="como-se-calcula-chevron" aria-hidden="true" />
      </summary>
      <div className="como-se-calcula-cuerpo">{children}</div>
    </details>
  );
}
