"use client";

/**
 * HU-19 · Crea la evaluación pública (aviso aceptado + rubro + token de Turnstile).
 * Devuelve la clave una sola vez; el token de sesión queda en la cookie httpOnly.
 */
import { useCallback, useRef, useState } from "react";
import { comoErrorEncuesta, pedir } from "@/lib/encuesta/cliente";
import type { ErrorEncuesta, Iniciada, IniciarEntrada } from "@/lib/encuesta/contratos";

export function useIniciarEvaluacion() {
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<ErrorEncuesta | null>(null);
  const enCurso = useRef(false); // evita el doble envío (doble clic / Enter repetido)

  const iniciar = useCallback(async (entrada: IniciarEntrada): Promise<Iniciada | null> => {
    if (enCurso.current) return null;
    enCurso.current = true;
    setEnviando(true);
    setError(null);
    try {
      return await pedir<Iniciada>("/bff/encuesta/iniciar", { method: "POST", json: entrada });
    } catch (e) {
      setError(comoErrorEncuesta(e));
      return null;
    } finally {
      enCurso.current = false;
      setEnviando(false);
    }
  }, []);

  return { iniciar, enviando, error, limpiarError: () => setError(null) };
}
