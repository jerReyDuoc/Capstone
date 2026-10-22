"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, cargarPanel, evaluacionDelEncuestado, listarEvaluaciones, MODO_DEMO, sesionEncuestado, type BaseApi } from "@/lib/api";
import type { EvaluacionApi, PanelVista } from "@/lib/types";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "listo"; panel: PanelVista }
  | { tipo: "sin-evaluaciones" }
  | { tipo: "sin-resumen"; mensaje: string }
  | { tipo: "error"; mensaje: string };

/**
 * "interno": equipo de TherionLabs (lista todas las evaluaciones, lee /api).
 * "encuestado": quien completó el autodiagnóstico desde la landing (HU-19/20). Ve solo su
 * evaluación y todo se lee por el BFF (/bff/api), que agrega su token.
 */
export type ModoPanel = "detectando" | "interno" | "encuestado";

interface PanelContexto {
  estado: Estado;
  modo: ModoPanel;
  evaluaciones: EvaluacionApi[];
  evaluacionId: number | null;
  demo: boolean;
  seleccionarEvaluacion: (id: number) => void;
  recargar: () => void;
  /** Construye un href conservando la evaluación seleccionada. */
  href: (ruta: string, extra?: Record<string, string>) => string;
}

const Ctx = createContext<PanelContexto | null>(null);

export function PanelProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const idUrl = Number(params.get("evaluacion")) || null;

  const [evaluaciones, setEvaluaciones] = useState<EvaluacionApi[]>([]);
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });
  const [version, setVersion] = useState(0);
  const [modo, setModo] = useState<ModoPanel>("detectando");
  const base: BaseApi = modo === "encuestado" ? "/bff/api" : "/api";

  // ¿Quien mira es un encuestado con sesión? Si la URL pide otra evaluación, se trata
  // como acceso interno (el BFF igual rechazaría cualquier evaluación que no sea la suya).
  useEffect(() => {
    const ctrl = new AbortController();
    sesionEncuestado(ctrl.signal)
      .then((id) => setModo(id != null && (idUrl == null || idUrl === id) ? "encuestado" : "interno"))
      .catch((e) => {
        if (e.name !== "AbortError") setModo("interno");
      });
    return () => ctrl.abort();
  }, [idUrl]);

  // Preferimos evaluaciones completadas: son las que tienen resumen definitivo.
  const evaluacionId = useMemo(() => {
    if (idUrl) return idUrl;
    const completada = evaluaciones.find((e) => e.estado_progreso === "completada");
    return (completada ?? evaluaciones[0])?.id ?? null;
  }, [idUrl, evaluaciones]);

  useEffect(() => {
    if (modo === "detectando") return;
    const ctrl = new AbortController();
    const pedido =
      modo === "encuestado"
        ? sesionEncuestado(ctrl.signal).then(async (id) =>
            id == null ? [] : [await evaluacionDelEncuestado(id, ctrl.signal)],
          )
        : listarEvaluaciones(ctrl.signal);
    pedido
      .then((lista) => {
        setEvaluaciones(lista);
        if (lista.length === 0 && !idUrl) setEstado({ tipo: "sin-evaluaciones" });
      })
      .catch((e) => {
        if (e.name !== "AbortError") setEstado({ tipo: "error", mensaje: (e as Error).message });
      });
    return () => ctrl.abort();
  }, [version, idUrl, modo]);

  useEffect(() => {
    if (evaluacionId == null || modo === "detectando") return;
    const ctrl = new AbortController();
    setEstado({ tipo: "cargando" });
    cargarPanel(evaluacionId, ctrl.signal, base)
      .then((panel) => setEstado({ tipo: "listo", panel }))
      .catch((e) => {
        if (e.name === "AbortError") return;
        if (e instanceof ApiError && e.status === 404) {
          setEstado({ tipo: "sin-resumen", mensaje: e.message });
        } else {
          setEstado({ tipo: "error", mensaje: (e as Error).message });
        }
      });
    return () => ctrl.abort();
  }, [evaluacionId, version, modo, base]);

  const href = useCallback(
    (ruta: string, extra: Record<string, string> = {}) => {
      const q = new URLSearchParams();
      if (evaluacionId) q.set("evaluacion", String(evaluacionId));
      for (const [k, v] of Object.entries(extra)) if (v) q.set(k, v);
      const s = q.toString();
      return s ? `${ruta}?${s}` : ruta;
    },
    [evaluacionId],
  );

  const seleccionarEvaluacion = useCallback(
    (id: number) => {
      const q = new URLSearchParams(params.toString());
      q.set("evaluacion", String(id));
      router.push(`${pathname}?${q.toString()}`);
    },
    [params, pathname, router],
  );

  const valor = useMemo<PanelContexto>(
    () => ({
      estado,
      modo,
      evaluaciones,
      evaluacionId,
      demo: MODO_DEMO,
      seleccionarEvaluacion,
      recargar: () => setVersion((v) => v + 1),
      href,
    }),
    [estado, modo, evaluaciones, evaluacionId, seleccionarEvaluacion, href],
  );

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function usePanel() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("usePanel debe usarse dentro de <PanelProvider>");
  return ctx;
}
