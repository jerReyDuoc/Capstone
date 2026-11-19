/**
 * Corrección 18-11 · Tema de la interfaz: claro, oscuro (el de siempre) o azul.
 *
 * Se aplica con <html data-theme="…">; los colores son tokens de app/globals.css (cada tema solo cambia
 * tokens, así los componentes que ya usan var(--…) lo respetan sin tocarlos).
 *
 * Dónde se guarda (localStorage; el backend aún no tiene preferencias de usuario):
 *   - `tema:<usuarioId>`  la elección de cada cuenta de empresa;
 *   - `tema`              la última elección en este navegador: la lee SCRIPT_TEMA antes de pintar (sin
 *                         parpadeo) y la usan las páginas sin cuenta (portada, encuesta, panel interno).
 * Es una preferencia de pantalla, no un dato de la cuenta: cerrar sesión no la borra.
 *
 * Lógica pura y probada en tests/tema.test.ts (incluido el hash de SCRIPT_TEMA para la CSP).
 */
import type { IconName } from "@/components/ui/Icon";

export type Tema = "light" | "dark" | "blue";

export const TEMA_POR_DEFECTO: Tema = "dark";
export const CLAVE_TEMA = "tema";
export const claveTemaUsuario = (usuarioId: number) => `${CLAVE_TEMA}:${usuarioId}`;

export const TEMAS: { id: Tema; texto: string; icono: IconName }[] = [
  { id: "light", texto: "Claro", icono: "sol" },
  { id: "dark", texto: "Oscuro", icono: "luna" },
  { id: "blue", texto: "Azul", icono: "gota" },
];

/** Color de la barra del navegador móvil (<meta name="theme-color">), igual a --bg de cada tema. */
export const COLOR_NAVEGADOR: Record<Tema, string> = { dark: "#050807", light: "#f7f6f2", blue: "#06101d" };

export const esTema = (v: unknown): v is Tema => v === "light" || v === "dark" || v === "blue";

type Lectura = Pick<Storage, "getItem">;
type Escritura = Pick<Storage, "setItem">;

/** El tema de la cuenta; si no eligió, el último de este navegador; si no, el oscuro. */
export function leerTema(almacen: Lectura | null, usuarioId: number | null = null): Tema {
  try {
    const propio = usuarioId != null ? almacen?.getItem(claveTemaUsuario(usuarioId)) : null;
    if (esTema(propio)) return propio;
    const global = almacen?.getItem(CLAVE_TEMA);
    return esTema(global) ? global : TEMA_POR_DEFECTO;
  } catch {
    return TEMA_POR_DEFECTO;
  }
}

export function guardarTema(almacen: Escritura | null, tema: Tema, usuarioId: number | null = null): void {
  try {
    almacen?.setItem(CLAVE_TEMA, tema);
    if (usuarioId != null) almacen?.setItem(claveTemaUsuario(usuarioId), tema);
  } catch {
    /* sin almacenamiento (modo privado): el tema dura lo que dure la página */
  }
}

/** Evento que avisa a todos los selectores de la página (p. ej. el de escritorio y el de móvil) del cambio. */
export const EVENTO_TEMA = "cai:tema";

export function aplicarTema(tema: Tema): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = tema;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", COLOR_NAVEGADOR[tema]);
  window.dispatchEvent(new CustomEvent<Tema>(EVENTO_TEMA, { detail: tema }));
}

/** El tema que sigue al actual (el botón único de pantallas angostas los recorre en orden). */
export function temaSiguiente(actual: Tema): Tema {
  const i = TEMAS.findIndex((t) => t.id === actual);
  return TEMAS[(i + 1) % TEMAS.length].id;
}

/**
 * Script en línea del <head> (app/layout.tsx): pone el tema antes de pintar. NO cambiarlo sin actualizar
 * HASH_SCRIPT_TEMA: las páginas con CSP de nonce (middleware.ts → cspFlujo) lo permiten por su hash.
 */
export const SCRIPT_TEMA =
  'try{var t=localStorage.getItem("tema");if(t==="light"||t==="dark"||t==="blue")document.documentElement.dataset.theme=t}catch(e){}';

/** 'sha256-…' de SCRIPT_TEMA (lo verifica tests/tema.test.ts). */
export const HASH_SCRIPT_TEMA = "sha256-aYLLHJh8fxdfEMdA2ZUXTjGFAS26YObjvjnHrxN0tBc=";
