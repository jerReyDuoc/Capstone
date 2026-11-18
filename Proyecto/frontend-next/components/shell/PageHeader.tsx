"use client";

import { useEffect, useId, type ReactNode } from "react";
import { Actualizado } from "@/components/ui/Actualizado";
import { useActualizacionAutomatica } from "@/hooks/useActualizacionAutomatica";
import { usePanel } from "@/hooks/usePanel";

const fecha = (iso: string | null) =>
  iso ? new Intl.DateTimeFormat("es-CL", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(`${iso}T12:00:00`)) : "sin fecha";

/**
 * Encabezado de las páginas del panel.
 * Auditoría UX 16-11 · Fase 5.D: sin botón "Actualizar" por página. Los datos se recargan solos
 * al volver a la pestaña (sin esqueleto) y se muestra "Actualizado hace X" con un ícono pequeño
 * para forzar la recarga.
 */
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
  const { evaluaciones, evaluacionId, seleccionarEvaluacion, recargarSilencioso, estado } = usePanel();
  const actualizacion = useActualizacionAutomatica(recargarSilencioso);
  const { marcar } = actualizacion;
  const listo = estado.tipo === "listo";
  // La primera carga cuenta como "actualizado"
  useEffect(() => {
    if (listo) marcar();
  }, [listo, marcar]);
  const idSelect = useId();
  // Correcciones 29-10: el selector solo aparece cuando hay algo que elegir (≥2 completadas).
  const completadas = evaluaciones
    .filter((e) => e.estado_progreso === "completada")
    .sort((a, b) => b.id - a.id);
  const mostrarSelector = completadas.length >= 2;

  return (
    <header className="page-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1 className="page-title">{titulo}</h1>
        <p className="page-sub">{subtitulo}</p>
      </div>
      <div className="page-actions">
        {children}
        {mostrarSelector ? (
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
              {completadas.map((e, i) => (
                <option key={e.id} value={e.id}>
                  {i === 0 ? "Más reciente" : `Evaluación ${completadas.length - i}`} · {fecha(e.fecha_inicio)}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <Actualizado estado={actualizacion} />
      </div>
    </header>
  );
}
