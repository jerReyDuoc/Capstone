"use client";

import { useCallback, useEffect, useState } from "react";
import type { FiltrosBrechas } from "@/lib/filtrosBrechas";
import { buscarVista, fijarVista, leerVistas, quitarVista, suscribirVistas, type VistaFijada } from "@/lib/vistasFijadas";

/** HU-11 · Vistas de brechas fijadas en el Diagnóstico (sincronizadas entre componentes y pestañas). */
export function useVistasFijadas(evaluacionId: number | null) {
  // Se lee en un efecto para no desalinear el HTML del servidor con el del navegador.
  const [todas, setTodas] = useState<VistaFijada[]>([]);

  useEffect(() => {
    const cargar = () => setTodas(leerVistas());
    cargar();
    return suscribirVistas(cargar);
  }, []);

  const vistas = evaluacionId == null ? [] : todas.filter((v) => v.evaluacionId === evaluacionId);

  const estaFijada = useCallback(
    (filtros: FiltrosBrechas) => (evaluacionId == null ? undefined : buscarVista(todas, evaluacionId, filtros)),
    [todas, evaluacionId],
  );

  const fijar = useCallback(
    (filtros: FiltrosBrechas) => (evaluacionId == null ? false : fijarVista(evaluacionId, filtros)),
    [evaluacionId],
  );

  const quitar = useCallback((id: string) => quitarVista(id), []);

  return { vistas, estaFijada, fijar, quitar };
}
