"use client";

/**
 * Auditoría UX 16-11 · Fase 9.6: marca <html data-teclado> mientras la persona navega con el
 * teclado (Tab o flechas) y lo quita al usar el mouse o el dedo. Así los números de atajo de
 * cada opción solo se muestran a quien los puede usar.
 */
import { useEffect } from "react";

export function DeteccionTeclado() {
  useEffect(() => {
    const raiz = document.documentElement;
    const teclado = (e: KeyboardEvent) => {
      if (e.key === "Tab" || e.key.startsWith("Arrow")) raiz.dataset.teclado = "";
    };
    const puntero = () => delete raiz.dataset.teclado;
    window.addEventListener("keydown", teclado, true);
    window.addEventListener("pointerdown", puntero, true);
    return () => {
      window.removeEventListener("keydown", teclado, true);
      window.removeEventListener("pointerdown", puntero, true);
    };
  }, []);
  return null;
}
