"use client";

/**
 * HU-19 · Evidencias y validaciones con IA restantes hoy (cuota diaria del LLM).
 * Llamar a `refrescar()` después de subir una evidencia o al recibir un 429 de cuota.
 */
import { useCallback, useEffect, useState } from "react";
import { pedir } from "@/lib/encuesta/cliente";
import { parseLimites, type Limites } from "@/lib/encuesta/contratos";

export function useLimitesEncuesta(activo = true) {
  const [limites, setLimites] = useState<Limites | null>(null);
  const [error, setError] = useState(false);

  const refrescar = useCallback(async () => {
    try {
      const r = parseLimites(await pedir<unknown>("/bff/api/encuesta-publica/limites"));
      if (r.ok) {
        setLimites(r.valor);
        setError(false);
      }
    } catch {
      setError(true); // los límites son informativos: si fallan, el flujo sigue
    }
  }, []);

  useEffect(() => {
    if (activo) void refrescar();
  }, [activo, refrescar]);

  return { limites, error, refrescar };
}
