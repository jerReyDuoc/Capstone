/**
 * HU-11 · "Exportar al dashboard": el gestor fija un listado filtrado (p. ej. las brechas
 * críticas de Protección de Datos) y aparece como tarjeta en el Diagnóstico.
 *
 * Se guarda en localStorage del navegador: el backend aún no tiene preferencias de usuario.
 * Solo se guardan los FILTROS, nunca las brechas: los conteos se recalculan con los datos
 * vigentes de la evaluación, así la tarjeta nunca queda desactualizada.
 * Cuando exista un endpoint de preferencias basta con reemplazar `almacen`.
 */
import { filtrosAParams, filtrosDesdeParams, mismosFiltros, type FiltrosBrechas } from "./filtrosBrechas";

export interface VistaFijada {
  id: string;
  evaluacionId: number;
  filtros: FiltrosBrechas;
  creada: string; // ISO
}

export const CLAVE_ALMACEN = "complianceai.hu11.vistas-fijadas.v1";
export const MAX_VISTAS = 4;

/** Abstracción mínima de Storage para poder probarlo sin navegador. */
export interface Almacen {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
}

function almacenNavegador(): Almacen | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null; // modo privado / almacenamiento bloqueado
  }
}

type Guardada = { id: string; evaluacionId: number; params: Record<string, string>; creada: string };

export function leerVistas(almacen: Almacen | null = almacenNavegador()): VistaFijada[] {
  if (!almacen) return [];
  try {
    const crudo = JSON.parse(almacen.getItem(CLAVE_ALMACEN) ?? "[]") as Guardada[];
    if (!Array.isArray(crudo)) return [];
    return crudo
      .filter((v) => v && typeof v.id === "string" && Number.isInteger(v.evaluacionId))
      .map((v) => ({
        id: v.id,
        evaluacionId: v.evaluacionId,
        creada: v.creada,
        filtros: filtrosDesdeParams({ get: (k) => v.params?.[k] ?? null }),
      }));
  } catch {
    return [];
  }
}

function escribir(vistas: VistaFijada[], almacen: Almacen | null): boolean {
  if (!almacen) return false;
  try {
    const guardar: Guardada[] = vistas.map((v) => ({
      id: v.id,
      evaluacionId: v.evaluacionId,
      creada: v.creada,
      params: filtrosAParams(v.filtros),
    }));
    almacen.setItem(CLAVE_ALMACEN, JSON.stringify(guardar));
    notificar();
    return true;
  } catch {
    return false; // cuota llena o bloqueado
  }
}

export function buscarVista(vistas: VistaFijada[], evaluacionId: number, filtros: FiltrosBrechas) {
  return vistas.find((v) => v.evaluacionId === evaluacionId && mismosFiltros(v.filtros, filtros));
}

/**
 * Fija una vista (si ya existe no duplica). Si se supera el máximo, sale la más antigua
 * de la misma evaluación. Devuelve false si el navegador no permite guardar.
 */
export function fijarVista(
  evaluacionId: number,
  filtros: FiltrosBrechas,
  almacen: Almacen | null = almacenNavegador(),
  ahora: Date = new Date(),
): boolean {
  const vistas = leerVistas(almacen);
  if (buscarVista(vistas, evaluacionId, filtros)) return true;
  const nueva: VistaFijada = {
    id: `${evaluacionId}-${ahora.getTime().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    evaluacionId,
    filtros,
    creada: ahora.toISOString(),
  };
  const deEsta = vistas.filter((v) => v.evaluacionId === evaluacionId);
  const otras = vistas.filter((v) => v.evaluacionId !== evaluacionId);
  const recortadas = [...deEsta, nueva].slice(-MAX_VISTAS);
  return escribir([...otras, ...recortadas], almacen);
}

export function quitarVista(id: string, almacen: Almacen | null = almacenNavegador()): boolean {
  return escribir(
    leerVistas(almacen).filter((v) => v.id !== id),
    almacen,
  );
}

/* Aviso entre componentes de la misma pestaña (el evento "storage" solo llega a OTRAS pestañas). */
const EVENTO = "complianceai:vistas-fijadas";
function notificar() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EVENTO));
}
export function suscribirVistas(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const alStorage = (e: StorageEvent) => {
    if (e.key === CLAVE_ALMACEN) cb();
  };
  window.addEventListener(EVENTO, cb);
  window.addEventListener("storage", alStorage);
  return () => {
    window.removeEventListener(EVENTO, cb);
    window.removeEventListener("storage", alStorage);
  };
}
