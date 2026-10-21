"use client";

/**
 * HU-19 · Widget de Cloudflare Turnstile (CAPTCHA, normalmente invisible).
 *
 * - El script se carga SOLO cuando este componente se monta (paso 2 del flujo): la
 *   landing nunca lo descarga.
 * - appearance "interaction-only": la persona solo ve algo si Cloudflare necesita que
 *   haga clic; en la mayoría de los casos el token llega solo.
 * - El token es de un solo uso y dura 300 s: al vencer o tras un envío fallido se
 *   reinicia con `control.reset()`. El servidor lo valida (nunca se confía aquí).
 */
import { useEffect, useRef, type RefObject } from "react";

interface OpcionesTurnstile {
  sitekey: string;
  action?: string;
  theme?: "light" | "dark" | "auto";
  language?: string;
  appearance?: "always" | "execute" | "interaction-only";
  callback?: (token: string) => void;
  "expired-callback"?: () => void;
  "error-callback"?: () => void;
  "timeout-callback"?: () => void;
}

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opciones: OpcionesTurnstile) => string;
      reset: (id?: string) => void;
      remove: (id?: string) => void;
    };
  }
}

const URL_SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let cargando: Promise<void> | null = null;

function cargarScript(nonce?: string): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.turnstile) return Promise.resolve();
  if (!cargando) {
    cargando = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = URL_SCRIPT;
      script.async = true;
      if (nonce) script.nonce = nonce;
      script.onload = () => resolve();
      script.onerror = () => {
        cargando = null;
        reject(new Error("turnstile"));
      };
      document.head.appendChild(script);
    });
  }
  return cargando;
}

export interface ControlTurnstile {
  reset: () => void;
}

export function Turnstile({
  siteKey,
  nonce,
  accion = "iniciar_encuesta",
  onToken,
  onError,
  control,
}: {
  siteKey: string;
  nonce?: string;
  accion?: string;
  onToken: (token: string | null) => void;
  onError?: () => void;
  control?: RefObject<ControlTurnstile | null>;
}) {
  const contenedor = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  // Callbacks siempre frescos sin volver a renderizar el widget
  const cb = useRef({ onToken, onError });
  cb.current = { onToken, onError };

  useEffect(() => {
    let cancelado = false;
    cargarScript(nonce)
      .then(() => {
        if (cancelado || !contenedor.current || !window.turnstile) return;
        widgetId.current = window.turnstile.render(contenedor.current, {
          sitekey: siteKey,
          action: accion,
          theme: "dark",
          language: "es",
          appearance: "interaction-only",
          callback: (t) => cb.current.onToken(t),
          "expired-callback": () => cb.current.onToken(null),
          "timeout-callback": () => cb.current.onToken(null),
          "error-callback": () => {
            cb.current.onToken(null);
            cb.current.onError?.();
          },
        });
      })
      .catch(() => cb.current.onError?.());
    return () => {
      cancelado = true;
      if (widgetId.current && window.turnstile) window.turnstile.remove(widgetId.current);
      widgetId.current = null;
    };
  }, [siteKey, accion, nonce]);

  useEffect(() => {
    if (!control) return;
    control.current = {
      reset: () => {
        cb.current.onToken(null);
        if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current);
      },
    };
    return () => {
      control.current = null;
    };
  }, [control]);

  return <div ref={contenedor} />;
}
