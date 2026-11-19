"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ApiError,
  cargarPanel,
  evaluacionDelEncuestado,
  listarEvaluaciones,
  MODO_DEMO,
  sesionCliente,
  sesionEncuestado,
  type BaseApi,
} from "@/lib/api";
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
 * "cliente": usuario definitivo de una empresa cliente (HU-28). Ve las evaluaciones migradas
 * a su empresa y todo se lee por /bff/cliente/api (su token vive en otra cookie httpOnly).
 */
export type ModoPanel = "detectando" | "interno" | "encuestado" | "cliente";

const BASE_DE: Record<ModoPanel, BaseApi> = {
  detectando: "/api",
  interno: "/api",
  encuestado: "/bff/api",
  cliente: "/bff/cliente/api",
};

interface PanelContexto {
  estado: Estado;
  modo: ModoPanel;
  evaluaciones: EvaluacionApi[];
  evaluacionId: number | null;
  /** De dónde leer los datos según el modo (para componentes que piden algo más: PDF, plan…). */
  base: BaseApi;
  demo: boolean;
  seleccionarEvaluacion: (id: number) => void;
  recargar: () => void;
  /**
   * Auditoría UX 16-11: recarga sin mostrar el esqueleto (al volver a la pestaña). Resuelve
   * cuando los datos nuevos llegaron.
   */
  recargarSilencioso: () => Promise<void>;
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
  // Recarga silenciosa: conserva lo que se ve mientras llegan los datos nuevos
  const silencioso = useRef(false);
  const alTerminar = useRef<(() => void) | null>(null);
  const [modo, setModo] = useState<ModoPanel>("detectando");
  const base = BASE_DE[modo];

  // Corrección 18-11 (2): la sesión de la EMPRESA manda. Antes ganaba la del encuestado: quien hizo el
  // autodiagnóstico sin cuenta y después inició sesión en el mismo navegador entraba a /panel/* como encuestado
  // (menú gratuito, sin "Mi empresa") y no podía volver. El login ya borra la cookie del encuestado
  // (app/bff/cliente/login); esto cubre a quien ya tenía las dos cookies.
  // Si no hay sesión de empresa: ¿es un encuestado con sesión? Si la URL pide otra evaluación, se trata
  // como acceso interno (el BFF igual rechazaría cualquier evaluación que no sea la suya).
  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([sesionEncuestado(ctrl.signal), sesionCliente(ctrl.signal)])
      .then(([id, cliente]) =>
        setModo(cliente ? "cliente" : id != null && (idUrl == null || idUrl === id) ? "encuestado" : "interno"),
      )
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
        : listarEvaluaciones(ctrl.signal, base);
    pedido
      .then((lista) => {
        setEvaluaciones(lista);
        if (lista.length === 0 && !idUrl) setEstado({ tipo: "sin-evaluaciones" });
      })
      .catch((e) => {
        if (e.name !== "AbortError") setEstado({ tipo: "error", mensaje: (e as Error).message });
      });
    return () => ctrl.abort();
  }, [version, idUrl, modo, base]);

  useEffect(() => {
    if (evaluacionId == null || modo === "detectando") return;
    const ctrl = new AbortController();
    const sinEsqueleto = silencioso.current;
    silencioso.current = false;
    if (!sinEsqueleto) setEstado({ tipo: "cargando" });
    const terminar = () => {
      alTerminar.current?.();
      alTerminar.current = null;
    };
    cargarPanel(evaluacionId, ctrl.signal, base)
      .then((panel) => setEstado({ tipo: "listo", panel }))
      .then(terminar)
      .catch((e) => {
        if (e.name === "AbortError") return;
        terminar();
        // Si falla una recarga silenciosa, se conserva lo que ya se veía
        if (sinEsqueleto) return;
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
      base,
      demo: MODO_DEMO,
      seleccionarEvaluacion,
      recargar: () => setVersion((v) => v + 1),
      recargarSilencioso: () =>
        new Promise<void>((resolver) => {
          silencioso.current = true;
          alTerminar.current = resolver;
          setVersion((v) => v + 1);
        }),
      href,
    }),
    [estado, modo, evaluaciones, evaluacionId, base, seleccionarEvaluacion, href],
  );

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

/** Correcciones 29-10: la barra lateral también vive en /empresa, fuera de <PanelProvider>. */
export function usePanelOpcional(): PanelContexto | null {
  return useContext(Ctx);
}

export function usePanel() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("usePanel debe usarse dentro de <PanelProvider>");
  return ctx;
}
