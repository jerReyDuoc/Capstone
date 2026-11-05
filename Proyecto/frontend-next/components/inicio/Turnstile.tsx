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
 * - Correcciones 05-11: a algunas personas el desafío les fallaba ("no eres una persona")
 *   y solo salían recargando la página. Ahora el widget se recupera solo: ante un error
 *   se reinicia hasta 3 veces con espera creciente; si sigue fallando, o si en 25 s no
 *   llega el token, avisa con `onError` y `control.reiniciar()` lo vuelve a crear desde
 *   cero (lo usa el botón "Reintentar verificación"). Si el script no carga, también se
 *   puede volver a pedir.
 */
import { useEffect, useRef, useState, type RefObject } from "react";

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
  retry?: "auto" | "never";
  "retry-interval"?: number;
  "refresh-expired"?: "auto" | "manual" | "never";
  "refresh-timeout"?: "auto" | "manual" | "never";
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
  /** Pide un token nuevo con el mismo widget (tras un envío o un token vencido). */
  reset: () => void;
  /** Destruye el widget y lo crea de nuevo (recuperación manual, sin recargar la página). */
  reiniciar: () => void;
}

const REINTENTOS_AUTOMATICOS = 3;
const ESPERA_TOKEN_MS = 25_000;

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
  // Cambiarla vuelve a montar el widget desde cero (control.reiniciar)
  const [generacion, setGeneracion] = useState(0);
  // Callbacks siempre frescos sin volver a renderizar el widget
  const cb = useRef({ onToken, onError });
  cb.current = { onToken, onError };

  useEffect(() => {
    let cancelado = false;
    let fallos = 0;
    let reintento: ReturnType<typeof setTimeout> | undefined;
    let vigia: ReturnType<typeof setTimeout> | undefined;

    const armarVigia = () => {
      clearTimeout(vigia);
      vigia = setTimeout(() => {
        if (!cancelado) cb.current.onError?.();
      }, ESPERA_TOKEN_MS);
    };

    const reintentar = () => {
      fallos += 1;
      cb.current.onToken(null);
      if (fallos > REINTENTOS_AUTOMATICOS) {
        cb.current.onError?.();
        return;
      }
      clearTimeout(reintento);
      reintento = setTimeout(() => {
        if (cancelado || !widgetId.current || !window.turnstile) return;
        window.turnstile.reset(widgetId.current);
        armarVigia();
      }, 1200 * 2 ** (fallos - 1));
    };

    cargarScript(nonce)
      .then(() => {
        if (cancelado || !contenedor.current || !window.turnstile) return;
        armarVigia();
        widgetId.current = window.turnstile.render(contenedor.current, {
          sitekey: siteKey,
          action: accion,
          theme: "dark",
          language: "es",
          appearance: "interaction-only",
          retry: "auto",
          "retry-interval": 4000,
          "refresh-expired": "auto",
          "refresh-timeout": "auto",
          callback: (t) => {
            fallos = 0;
            clearTimeout(vigia);
            cb.current.onToken(t);
          },
          "expired-callback": () => cb.current.onToken(null),
          "timeout-callback": () => reintentar(),
          "error-callback": () => reintentar(),
        });
      })
      .catch(() => cb.current.onError?.());
    return () => {
      cancelado = true;
      clearTimeout(reintento);
      clearTimeout(vigia);
      if (widgetId.current && window.turnstile) window.turnstile.remove(widgetId.current);
      widgetId.current = null;
    };
  }, [siteKey, accion, nonce, generacion]);

  useEffect(() => {
    if (!control) return;
    control.current = {
      reset: () => {
        cb.current.onToken(null);
        if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current);
      },
      reiniciar: () => {
        cb.current.onToken(null);
        // Si el script de Cloudflare ni siquiera cargó (red, bloqueador o una política del
        // navegador), rearmar el widget no sirve: se recarga la página, como haría un F5.
        if (!window.turnstile) {
          window.location.reload();
          return;
        }
        setGeneracion((g) => g + 1);
      },
    };
    return () => {
      control.current = null;
    };
  }, [control]);

  // key: al reiniciar, React entrega un contenedor nuevo y vacío a Turnstile
  return <div ref={contenedor} key={generacion} />;
}
