"use client";

/**
 * Auditoría UX 16-11 · Fase 5.D: los datos se recargan solos al volver a la pestaña
 * (visibilitychange / focus), como mínimo cada 30 s, y se informa "Actualizado hace X".
 * Reemplaza al botón "Actualizar" de cada página; queda un ícono pequeño para forzar la recarga.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export const MIN_ENTRE_AUTOMATICAS_MS = 30_000;

export interface Actualizacion {
  ultima: Date | null;
  actualizando: boolean;
  actualizar: () => Promise<void>;
  /** Marca "recién actualizado" sin volver a pedir (p. ej. tras la carga inicial). */
  marcar: () => void;
}

export function useActualizacionAutomatica(recargar: () => Promise<unknown> | unknown, activo = true): Actualizacion {
  const [ultima, setUltima] = useState<Date | null>(null);
  const [actualizando, setActualizando] = useState(false);
  const fn = useRef(recargar);
  fn.current = recargar;
  const enCurso = useRef(false);
  const ultimaMs = useRef(Date.now());

  const marcar = useCallback(() => {
    const ahora = new Date();
    ultimaMs.current = ahora.getTime();
    setUltima(ahora);
  }, []);

  const actualizar = useCallback(async () => {
    if (enCurso.current) return;
    enCurso.current = true;
    setActualizando(true);
    try {
      await fn.current();
      marcar();
    } finally {
      enCurso.current = false;
      setActualizando(false);
    }
  }, [marcar]);

  useEffect(() => {
    if (!activo) return;
    const alVolver = () => {
      if (document.visibilityState === "visible" && Date.now() - ultimaMs.current > MIN_ENTRE_AUTOMATICAS_MS) {
        void actualizar();
      }
    };
    document.addEventListener("visibilitychange", alVolver);
    window.addEventListener("focus", alVolver);
    return () => {
      document.removeEventListener("visibilitychange", alVolver);
      window.removeEventListener("focus", alVolver);
    };
  }, [activo, actualizar]);

  return { ultima, actualizando, actualizar, marcar };
}
