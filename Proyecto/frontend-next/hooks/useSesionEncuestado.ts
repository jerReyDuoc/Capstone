"use client";

/**
 * HU-19 · Sesión del encuestado en el navegador.
 * El token no se ve desde aquí (cookie httpOnly): solo se sabe si hay sesión, de qué
 * evaluación es y cuándo vence. `cerrarSesion` borra la cookie en este dispositivo.
 */
import { useCallback, useEffect, useState } from "react";
import { pedir } from "@/lib/encuesta/cliente";
import type { Sesion } from "@/lib/encuesta/contratos";

type Estado = { tipo: "cargando" } | { tipo: "activa"; evaluacionId: number; expiraEn: number } | { tipo: "inactiva" } | { tipo: "error" };

export function useSesionEncuestado() {
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });

  const refrescar = useCallback(async () => {
    try {
      const s = await pedir<Sesion>("/bff/encuesta/sesion");
      setEstado(s.activa ? { tipo: "activa", evaluacionId: s.evaluacionId, expiraEn: s.expiraEn } : { tipo: "inactiva" });
    } catch {
      setEstado({ tipo: "error" });
    }
  }, []);

  useEffect(() => {
    void refrescar();
  }, [refrescar]);

  // Avisar cuando el token vence (8 h por defecto): la página puede pedir la clave de nuevo
  useEffect(() => {
    if (estado.tipo !== "activa") return;
    const ms = estado.expiraEn * 1000 - Date.now();
    if (ms <= 0) {
      setEstado({ tipo: "inactiva" });
      return;
    }
    const t = setTimeout(() => setEstado({ tipo: "inactiva" }), Math.min(ms, 2_147_000_000));
    return () => clearTimeout(t);
  }, [estado]);

  const cerrarSesion = useCallback(async () => {
    await pedir<void>("/bff/encuesta/sesion", { method: "DELETE" }).catch(() => undefined);
    setEstado({ tipo: "inactiva" });
  }, []);

  return { estado, refrescar, cerrarSesion };
}
