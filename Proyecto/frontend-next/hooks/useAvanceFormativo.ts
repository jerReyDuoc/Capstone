"use client";

import { useCallback, useEffect, useState } from "react";
import { usePanel } from "@/hooks/usePanel";
import { cargarAvance, mensajeFormacion } from "@/lib/formacion";
import type { AvanceFormativoApi } from "@/lib/types";

export type EstadoAvanceFormativo =
  | { tipo: "no-aplica" } // encuestado o equipo interno: el recorrido es del servicio contratado
  | { tipo: "cargando" }
  | { tipo: "listo"; avance: AvanceFormativoApi }
  | { tipo: "error"; mensaje: string };

/**
 * HU-26 · Avance formativo de la empresa para la evaluación seleccionada en el panel.
 * Solo existe para el usuario definitivo (modo "cliente"); en los demás modos el plan se
 * muestra igual (HU-12), sin recorrido ni avance.
 */
export function useAvanceFormativo(): { estado: EstadoAvanceFormativo; recargar: () => void } {
  const { modo, evaluacionId, estado: panel } = usePanel();
  const [estado, setEstado] = useState<EstadoAvanceFormativo>({ tipo: "no-aplica" });
  const [version, setVersion] = useState(0);
  const listo = panel.tipo === "listo";

  useEffect(() => {
    if (modo !== "cliente") {
      setEstado({ tipo: "no-aplica" });
      return;
    }
    if (!listo || evaluacionId == null) return;
    let vigente = true;
    setEstado((e) => (e.tipo === "listo" ? e : { tipo: "cargando" }));
    cargarAvance(evaluacionId)
      .then((avance) => vigente && setEstado({ tipo: "listo", avance }))
      .catch((e) => vigente && setEstado({ tipo: "error", mensaje: mensajeFormacion(e) }));
    return () => {
      vigente = false;
    };
  }, [modo, evaluacionId, listo, version]);

  const recargar = useCallback(() => setVersion((v) => v + 1), []);
  return { estado, recargar };
}
