/**
 * Corrección 18-11 · Lo que el NAVEGADOR guarda de una cuenta (sessionStorage/localStorage) lleva su dueño.
 *
 * Problema que corrige: la conversación del asistente de registro se guardaba con una clave fija; al cerrar
 * sesión y entrar con otra cuenta en la misma pestaña, la segunda veía la conversación de la primera.
 *
 *   - `usuarioClienteActual()` pregunta al BFF quién es la cuenta (el token es httpOnly: el JS no lo lee). No se
 *     guarda en una variable del módulo a propósito: un valor así sobreviviría al cambio de cuenta.
 *   - `limpiarDatosDeCuenta()` borra todo lo guardado por cuenta. Se llama al cerrar sesión y al iniciar sesión
 *     (si la sesión venció sin cerrar, quien entra después en la misma pestaña tampoco hereda nada).
 *
 * Las preferencias que no son datos de la cuenta (p. ej. la guía del mapa plegada) no se tocan.
 */
import { pedir } from "@/lib/encuesta/cliente";
import { PREFIJO_ALMACEN_GUIA } from "@/lib/guiaRegistro";

/** Prefijos de las claves del navegador que pertenecen a una cuenta. */
export const PREFIJOS_DE_CUENTA = [PREFIJO_ALMACEN_GUIA] as const;

type Almacen = Pick<Storage, "length" | "key" | "removeItem">;

export function borrarClavesConPrefijo(almacen: Almacen | null | undefined, prefijos: readonly string[]): number {
  if (!almacen) return 0;
  try {
    const claves: string[] = [];
    for (let i = 0; i < almacen.length; i++) {
      const k = almacen.key(i);
      if (k && prefijos.some((p) => k.startsWith(p))) claves.push(k);
    }
    claves.forEach((k) => almacen.removeItem(k));
    return claves.length;
  } catch {
    return 0; // sin almacenamiento (modo privado): no hay nada que borrar
  }
}

export function limpiarDatosDeCuenta(): void {
  if (typeof window === "undefined") return;
  for (const almacen of [window.sessionStorage, window.localStorage]) borrarClavesConPrefijo(almacen, PREFIJOS_DE_CUENTA);
}

/** Id del usuario definitivo con sesión en este navegador, o null (sin sesión o sin conexión). */
export async function usuarioClienteActual(signal?: AbortSignal): Promise<number | null> {
  try {
    const s = await pedir<{ activa: boolean; usuarioId?: number }>("/bff/cliente/sesion", { signal });
    return s.activa && typeof s.usuarioId === "number" ? s.usuarioId : null;
  } catch {
    return null;
  }
}
