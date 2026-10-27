"use client";

import { useEffect, useState } from "react";
import { usePanel } from "@/hooks/usePanel";
import { ApiError, cargarPlanFormativo } from "@/lib/api";
import type { PlanFormativoApi } from "@/lib/types";

export type EstadoPlan =
  | { tipo: "cargando" }
  | { tipo: "listo"; plan: PlanFormativoApi }
  | { tipo: "no-disponible"; mensaje: string }
  | { tipo: "error"; mensaje: string };

/**
 * HU-12 · Plan formativo de la evaluación seleccionada en el panel. Se pide cuando el panel
 * terminó de cargar, así "Actualizar" (que recarga el panel) también recarga el plan.
 */
export function usePlanFormativo(): EstadoPlan {
  const { evaluacionId, modo, estado, base } = usePanel();
  const [plan, setPlan] = useState<EstadoPlan>({ tipo: "cargando" });
  const panelListo = estado.tipo === "listo";

  useEffect(() => {
    if (evaluacionId == null || modo === "detectando" || !panelListo) return;
    const ctrl = new AbortController();
    setPlan({ tipo: "cargando" });
    cargarPlanFormativo(evaluacionId, ctrl.signal, base)
      .then((p) => setPlan({ tipo: "listo", plan: p }))
      .catch((e) => {
        if ((e as Error).name === "AbortError") return;
        // 404 de un backend sin HU-12 (ruta inexistente) o sin resultados
        if (e instanceof ApiError && e.status === 404) {
          setPlan({
            tipo: "no-disponible",
            mensaje: e.codigo === "SIN_RESULTADOS" ? e.message : "El servidor aún no tiene el plan formativo (HU-12). Actualiza el backend.",
          });
        } else {
          setPlan({ tipo: "error", mensaje: (e as Error).message });
        }
      });
    return () => ctrl.abort();
  }, [evaluacionId, modo, panelListo, base]);

  return plan;
}
