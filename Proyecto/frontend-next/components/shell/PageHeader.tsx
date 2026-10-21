"use client";

import { useId, type ReactNode } from "react";
import { usePanel } from "@/hooks/usePanel";
import { Icon } from "@/components/ui/Icon";

const fecha = (iso: string | null) =>
  iso ? new Intl.DateTimeFormat("es-CL", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(`${iso}T12:00:00`)) : "sin fecha";

export function PageHeader({
  eyebrow,
  titulo,
  subtitulo,
  children,
}: {
  eyebrow: string;
  titulo: string;
  subtitulo: string;
  children?: ReactNode;
}) {
  const { evaluaciones, evaluacionId, seleccionarEvaluacion, recargar, estado } = usePanel();
  const idSelect = useId();

  return (
    <header className="page-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1 className="page-title">{titulo}</h1>
        <p className="page-sub">{subtitulo}</p>
      </div>
      <div className="page-actions">
        {children}
        {evaluaciones.length > 0 ? (
          <div className="field">
            <label className="field-label" htmlFor={idSelect}>
              Evaluación
            </label>
            <select
              id={idSelect}
              className="select"
              value={evaluacionId ?? ""}
              onChange={(e) => seleccionarEvaluacion(Number(e.target.value))}
            >
              {evaluaciones.map((e) => (
                <option key={e.id} value={e.id}>
                  #{e.id} · {fecha(e.fecha_inicio)}
                  {e.estado_progreso === "completada" ? "" : " · en curso"}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <button
          type="button"
          className="btn btn-ghost"
          onClick={recargar}
          aria-busy={estado.tipo === "cargando"}
          aria-label="Actualizar datos del panel"
        >
          <Icon name="refrescar" />
          Actualizar
        </button>
      </div>
    </header>
  );
}
