"use client";

/**
 * HU-01 / HU-02 · Estado del cuestionario del encuestado.
 *
 * Retoma donde quedó usando GET /progreso (`etapa`):
 *   filtro        → preguntas iniciales F1–F7 (adaptan qué controles aplican)
 *   cuestionario  → controles aplicables, empezando por el primero pendiente
 *   completo      → revisión final antes de completar
 *   cerrada       → la evaluación ya terminó: se ofrece ir a los resultados
 *
 * Cada respuesta se guarda al avanzar (upsert en el backend), así que cerrar la pestaña
 * nunca pierde trabajo.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "@/lib/cuestionario/api";
import type {
  ControlAplicableApi,
  EstadoDeclarado,
  EstadoFiltroApi,
  ProgresoApi,
  RespuestaDetalleApi,
} from "@/lib/cuestionario/modelo";
import { ordenarControles, respuestasFiltroGuardadas } from "@/lib/cuestionario/modelo";
import { comoErrorEncuesta } from "@/lib/encuesta/cliente";
import type { ErrorEncuesta } from "@/lib/encuesta/contratos";

export type Fase =
  | { tipo: "cargando" }
  | { tipo: "error"; error: ErrorEncuesta }
  | { tipo: "filtro" }
  | { tipo: "cuestionario" }
  | { tipo: "revision" }
  | { tipo: "cerrada" };

export function useCuestionario(evaluacionId: number) {
  const [fase, setFase] = useState<Fase>({ tipo: "cargando" });
  const [filtro, setFiltro] = useState<EstadoFiltroApi | null>(null);
  const [respuestasFiltro, setRespuestasFiltro] = useState<Record<string, boolean>>({});
  const [controles, setControles] = useState<ControlAplicableApi[]>([]);
  const [progreso, setProgreso] = useState<ProgresoApi | null>(null);
  const [indice, setIndice] = useState(0);
  const detalles = useRef(new Map<number, RespuestaDetalleApi>());
  const [versionDetalles, setVersionDetalles] = useState(0);

  /** id_control → respuesta guardada (id y estado declarado). */
  const respondidas = useMemo(() => {
    const m = new Map<number, { idRespuesta: number; estado: string | null; estadoFinal: string | null }>();
    for (const r of progreso?.respondidos ?? []) {
      m.set(r.id_control, { idRespuesta: r.id_respuesta, estado: r.estado_clasificacion, estadoFinal: r.estado_clasificacion_final });
    }
    return m;
  }, [progreso]);

  const refrescarProgreso = useCallback(async () => {
    const p = await api.obtenerProgreso(evaluacionId);
    setProgreso(p);
    return p;
  }, [evaluacionId]);

  const cargarFiltro = useCallback(async () => {
    const f = await api.obtenerFiltro(evaluacionId);
    setFiltro(f);
    setRespuestasFiltro(respuestasFiltroGuardadas(f));
    return f;
  }, [evaluacionId]);

  const cargar = useCallback(async () => {
    setFase({ tipo: "cargando" });
    try {
      const p = await refrescarProgreso();
      if (p.etapa === "cerrada") {
        setFase({ tipo: "cerrada" });
        return;
      }
      if (p.etapa === "filtro") {
        await cargarFiltro();
        setFase({ tipo: "filtro" });
        return;
      }
      const lista = ordenarControles(await api.controlesAplicables(evaluacionId));
      setControles(lista);
      if (p.etapa === "completo" || lista.length === 0) {
        setFase({ tipo: "revision" });
        return;
      }
      const siguiente = p.siguiente_control?.id_control;
      const i = lista.findIndex((c) => c.id_control === siguiente);
      setIndice(i >= 0 ? i : 0);
      setFase({ tipo: "cuestionario" });
    } catch (e) {
      setFase({ tipo: "error", error: comoErrorEncuesta(e) });
    }
  }, [evaluacionId, refrescarProgreso, cargarFiltro]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  /* ---------------------------------------------------------------- filtro */

  /** Rehacer las preguntas iniciales desde el cuestionario (permite corregir un error). */
  const editarFiltro = useCallback(async () => {
    try {
      await cargarFiltro();
      setFase({ tipo: "filtro" });
    } catch (e) {
      setFase({ tipo: "error", error: comoErrorEncuesta(e) });
    }
  }, [cargarFiltro]);

  const enviarFiltro = useCallback(
    async (cuerpo: { respuestas: { codigo: string; respuesta: boolean }[] }) => {
      const r = await api.guardarFiltro(evaluacionId, cuerpo); // los errores los muestra la pantalla
      await cargar();
      return r;
    },
    [evaluacionId, cargar],
  );

  /* ---------------------------------------------------------------- respuestas */

  const obtenerDetalle = useCallback(async (idRespuesta: number, forzar = false) => {
    const enCache = detalles.current.get(idRespuesta);
    if (enCache && !forzar) return enCache;
    const d = await api.obtenerRespuesta(idRespuesta);
    detalles.current.set(idRespuesta, d);
    setVersionDetalles((v) => v + 1);
    return d;
  }, []);

  const guardar = useCallback(
    async (control: ControlAplicableApi, estado: EstadoDeclarado, justificacion: string) => {
      const r = await api.guardarRespuesta(evaluacionId, control.id_control, estado, justificacion);
      detalles.current.delete(r.id_respuesta);
      await refrescarProgreso();
      return r.id_respuesta;
    },
    [evaluacionId, refrescarProgreso],
  );

  /** Tras guardar: siguiente control sin responder (o la revisión si no queda ninguno). */
  const avanzar = useCallback(
    (desde: number, respondidoAhora?: number) => {
      const respondido = (c: ControlAplicableApi) => c.id_control === respondidoAhora || respondidas.has(c.id_control);
      for (let paso = 1; paso <= controles.length; paso++) {
        const i = (desde + paso) % controles.length;
        if (!respondido(controles[i])) {
          setIndice(i);
          return;
        }
      }
      setFase({ tipo: "revision" });
    },
    [controles, respondidas],
  );

  const irA = useCallback(
    (i: number) => {
      setIndice(Math.max(0, Math.min(controles.length - 1, i)));
      setFase({ tipo: "cuestionario" });
    },
    [controles.length],
  );

  const irARevision = useCallback(() => setFase({ tipo: "revision" }), []);

  const completar = useCallback(async () => {
    await api.completarEvaluacion(evaluacionId);
  }, [evaluacionId]);

  return {
    fase,
    filtro,
    respuestasFiltro,
    setRespuestasFiltro,
    controles,
    progreso,
    indice,
    respondidas,
    detalles: detalles.current,
    versionDetalles,
    recargar: cargar,
    refrescarProgreso,
    editarFiltro,
    enviarFiltro,
    obtenerDetalle,
    guardar,
    avanzar,
    irA,
    irARevision,
    completar,
  };
}

export type Cuestionario = ReturnType<typeof useCuestionario>;
