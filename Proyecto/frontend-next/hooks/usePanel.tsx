"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, cargarPanel, listarEvaluaciones, MODO_DEMO } from "@/lib/api";
import type { EvaluacionApi, PanelVista } from "@/lib/types";

type Estado =
  | { tipo: "cargando" }
  | { tipo: "listo"; panel: PanelVista }
  | { tipo: "sin-evaluaciones" }
  | { tipo: "sin-resumen"; mensaje: string }
  | { tipo: "error"; mensaje: string };

interface PanelContexto {
  estado: Estado;
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

  // Preferimos evaluaciones completadas: son las que tienen resumen definitivo.
  const evaluacionId = useMemo(() => {
    if (idUrl) return idUrl;
    const completada = evaluaciones.find((e) => e.estado_progreso === "completada");
    return (completada ?? evaluaciones[0])?.id ?? null;
  }, [idUrl, evaluaciones]);

  useEffect(() => {
    const ctrl = new AbortController();
    listarEvaluaciones(ctrl.signal)
      .then((lista) => {
        setEvaluaciones(lista);
        if (lista.length === 0 && !idUrl) setEstado({ tipo: "sin-evaluaciones" });
      })
      .catch((e) => {
        if (e.name !== "AbortError") setEstado({ tipo: "error", mensaje: (e as Error).message });
      });
    return () => ctrl.abort();
  }, [version, idUrl]);

  useEffect(() => {
    if (evaluacionId == null) return;
    const ctrl = new AbortController();
    setEstado({ tipo: "cargando" });
    cargarPanel(evaluacionId, ctrl.signal)
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
  }, [evaluacionId, version]);

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
      evaluaciones,
      evaluacionId,
      demo: MODO_DEMO,
      seleccionarEvaluacion,
      recargar: () => setVersion((v) => v + 1),
      href,
    }),
    [estado, evaluaciones, evaluacionId, seleccionarEvaluacion, href],
  );

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function usePanel() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("usePanel debe usarse dentro de <PanelProvider>");
  return ctx;
}
