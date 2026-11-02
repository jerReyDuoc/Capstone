"use client";

import { useCallback, useEffect, useState } from "react";
import { usePanel } from "@/hooks/usePanel";
import { ApiError, cargarFichaInforme } from "@/lib/api";
import type { FichaInformeApi } from "@/lib/informe";

export type EstadoFicha =
  | { tipo: "cargando" }
  | { tipo: "listo"; ficha: FichaInformeApi }
  | { tipo: "no-disponible"; mensaje: string }
  | { tipo: "error"; mensaje: string };

/**
 * HU-21 · Ficha del informe de la evaluación seleccionada. Se pide cuando el panel terminó
 * de cargar, así "Actualizar" (que recarga el panel) también recarga la ficha.
 */
export function useFichaInforme(): { estado: EstadoFicha; reintentar: () => void } {
  const { evaluacionId, modo, estado: panel, base } = usePanel();
  const [estado, setEstado] = useState<EstadoFicha>({ tipo: "cargando" });
  const [intento, setIntento] = useState(0);
  const panelListo = panel.tipo === "listo";
  const reintentar = useCallback(() => setIntento((n) => n + 1), []);

  useEffect(() => {
    if (evaluacionId == null || modo === "detectando" || !panelListo) return;
    const ctrl = new AbortController();
    setEstado({ tipo: "cargando" });
    cargarFichaInforme(evaluacionId, ctrl.signal, base)
      .then((ficha) => setEstado({ tipo: "listo", ficha }))
      .catch((e) => {
        if ((e as Error).name === "AbortError") return;
        if (e instanceof ApiError && e.status === 404) {
          setEstado({
            tipo: "no-disponible",
            mensaje:
              e.codigo === "SIN_RESULTADOS"
                ? e.message
                : "El servidor todavía no entrega la ficha del informe. Actualiza el backend a la versión con HU-21.",
          });
        } else {
          setEstado({ tipo: "error", mensaje: (e as Error).message });
        }
      });
    return () => ctrl.abort();
  }, [evaluacionId, modo, panelListo, base, intento]);

  return { estado, reintentar };
}
