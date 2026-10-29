"use client";

import { useCallback, useRef, useState } from "react";
import { ErrorBff } from "@/lib/encuesta/cliente";
import {
  cambiarNivelConversacion,
  cargarContextoTutor,
  cargarConversacion,
  conversacionParaRetomar,
  crearConversacion,
  eliminarConversacion,
  enviarMensajeTutor,
  listarConversaciones,
  mensajeProvisional,
  mensajeTutor,
  tutorSinServicio,
} from "@/lib/tutor";
import type {
  ContextoTutorApi,
  ConversacionTutorApi,
  CuotaTutorApi,
  MensajeTutorApi,
  NivelFormativo,
} from "@/lib/types";

export type FaseTutor = "inactivo" | "cargando" | "listo" | "sin-servicio" | "error";

export interface EstadoTutor {
  fase: FaseTutor;
  contexto: ContextoTutorApi | null;
  conversaciones: ConversacionTutorApi[];
  conversacion: ConversacionTutorApi | null;
  mensajes: MensajeTutorApi[];
  nivel: NivelFormativo;
  cuota: CuotaTutorApi | null;
  enviando: boolean;
  error: string;
  /** HU-18: aviso del backend tras varios mensajes bloqueados; se limpia con el siguiente envío. */
  advertencia: string;
}

const INICIAL: EstadoTutor = {
  fase: "inactivo", contexto: null, conversaciones: [], conversacion: null, mensajes: [],
  nivel: "Inicial", cuota: null, enviando: false, error: "", advertencia: "",
};

/**
 * HU-15 · Estado del chat con el Agente IA Tutor.
 *
 * Al abrir carga el contexto (brechas de la evaluación vigente) y retoma la conversación
 * activa más reciente del mismo módulo; si no hay, la conversación se crea con el primer
 * mensaje (así no quedan conversaciones vacías). El nivel por defecto es el que sugiere el
 * backend (el de la ruta) y el usuario lo puede cambiar en cualquier momento.
 */
export function useTutor(rutaId: number | null) {
  const [estado, setEstado] = useState<EstadoTutor>(INICIAL);
  const enCurso = useRef<AbortController | null>(null);
  const parche = (p: Partial<EstadoTutor>) => setEstado((e) => ({ ...e, ...p }));

  const fallo = (e: unknown) =>
    tutorSinServicio(e)
      ? parche({ fase: "sin-servicio", error: mensajeTutor(e), enviando: false })
      : parche({ error: mensajeTutor(e), enviando: false });

  const iniciar = useCallback(async () => {
    setEstado((e) => ({ ...e, fase: e.fase === "listo" ? "listo" : "cargando", error: "" }));
    try {
      const [contexto, lista] = await Promise.all([cargarContextoTutor(rutaId), listarConversaciones()]);
      const retomar = conversacionParaRetomar(lista.items, rutaId);
      if (retomar) {
        const d = await cargarConversacion(retomar.id);
        setEstado((e) => ({
          ...e, fase: "listo", contexto, conversaciones: lista.items, conversacion: d.conversacion,
          mensajes: d.mensajes, nivel: d.conversacion.nivel, cuota: d.cuota ?? contexto.cuota ?? null, error: "",
        }));
      } else {
        setEstado((e) => ({
          ...e, fase: "listo", contexto, conversaciones: lista.items, conversacion: null, mensajes: [],
          nivel: contexto.nivel_sugerido, cuota: contexto.cuota ?? null, error: "",
        }));
      }
    } catch (e) {
      setEstado((s) => ({
        ...s, fase: tutorSinServicio(e) ? "sin-servicio" : "error", error: mensajeTutor(e),
      }));
    }
  }, [rutaId]);

  const refrescarLista = useCallback(async () => {
    try {
      const lista = await listarConversaciones();
      parche({ conversaciones: lista.items });
    } catch {
      /* la lista es secundaria */
    }
  }, []);

  /** Devuelve true si el mensaje se envió (el composer se limpia), false si hay que conservarlo. */
  const enviar = useCallback(
    async (texto: string): Promise<boolean> => {
      if (estado.enviando) return false;
      let conv = estado.conversacion;
      const provisional = mensajeProvisional(texto, estado.nivel);
      parche({ enviando: true, error: "", advertencia: "", mensajes: [...estado.mensajes, provisional] });
      try {
        if (!conv) {
          const creada = await crearConversacion(rutaId, estado.nivel);
          conv = creada.conversacion;
          parche({ conversacion: conv });
        }
        enCurso.current?.abort();
        const ctrl = new AbortController();
        enCurso.current = ctrl;
        const r = await enviarMensajeTutor(conv.id, texto, ctrl.signal);
        setEstado((e) => ({
          ...e,
          enviando: false,
          conversacion: r.conversacion,
          cuota: r.cuota,
          advertencia: r.advertencia ?? "",
          mensajes: [...e.mensajes.filter((m) => m.id !== provisional.id), r.mensaje_usuario, r.respuesta],
        }));
        void refrescarLista();
        return true;
      } catch (e) {
        if ((e as Error)?.name === "AbortError") return false;
        setEstado((s) => ({ ...s, mensajes: s.mensajes.filter((m) => m.id !== provisional.id) }));
        if (e instanceof ErrorBff && e.info.codigo === "CONVERSACION_DESACTUALIZADA" && conv) {
          parche({ conversacion: { ...conv, estado: "solo_lectura" } });
        }
        fallo(e);
        return false;
      }
    },
    [estado.enviando, estado.conversacion, estado.mensajes, estado.nivel, rutaId, refrescarLista],
  );

  const cambiarNivel = useCallback(
    async (nivel: NivelFormativo) => {
      const anterior = estado.nivel;
      parche({ nivel, error: "" });
      if (!estado.conversacion || estado.conversacion.estado !== "activa") return;
      try {
        const r = await cambiarNivelConversacion(estado.conversacion.id, nivel);
        parche({ conversacion: r.conversacion });
      } catch (e) {
        parche({ nivel: anterior });
        fallo(e);
      }
    },
    [estado.nivel, estado.conversacion],
  );

  const nueva = useCallback(() => {
    enCurso.current?.abort();
    setEstado((e) => ({
      ...e, conversacion: null, mensajes: [], enviando: false, error: "", advertencia: "",
      nivel: e.contexto?.nivel_sugerido ?? e.nivel,
    }));
  }, []);

  const abrir = useCallback(async (id: number) => {
    parche({ error: "" });
    try {
      const d = await cargarConversacion(id);
      parche({ conversacion: d.conversacion, mensajes: d.mensajes, nivel: d.conversacion.nivel, cuota: d.cuota ?? null });
    } catch (e) {
      fallo(e);
    }
  }, []);

  const borrar = useCallback(
    async (id: number) => {
      try {
        await eliminarConversacion(id);
        setEstado((e) => ({
          ...e,
          conversaciones: e.conversaciones.filter((c) => c.id !== id),
          ...(e.conversacion?.id === id
            ? { conversacion: null, mensajes: [], nivel: e.contexto?.nivel_sugerido ?? e.nivel }
            : {}),
        }));
      } catch (e) {
        fallo(e);
      }
    },
    [],
  );

  const limpiarError = useCallback(() => parche({ error: "" }), []);

  return { estado, iniciar, enviar, cambiarNivel, nueva, abrir, borrar, limpiarError };
}
