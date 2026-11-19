/**
 * Auditoría UX 16-11 · Fases 7 y 8.A: navegación organizada por TAREAS.
 *
 * Un solo modelo para la barra lateral (escritorio) y la barra inferior (móvil):
 *   Diagnóstico · Plan de acción · Privacidad y registro · Documentos   (+ "Mi empresa" arriba)
 *
 * - Cambia la organización del menú, NO las URL: todas las rutas existentes se conservan.
 * - Rótulos cortos que caben en una línea.
 * - El mapa de datos, el asistente y el registro de actividades son pasos de UN flujo
 *   ("Arma tu registro"): el menú tiene una sola entrada y el flujo muestra los pasos.
 * - Corrección 18-11: el asistente de registro TAMBIÉN es una sección propia ("Asistente"); dentro del mapa y
 *   del registro se sigue abriendo con su botón flotante.
 */
import type { IconName } from "@/components/ui/Icon";

export type ModoNavegacion = "cliente" | "encuestado" | "interno";

export interface EntradaNav {
  ruta: string;
  etiqueta: string;
  icono: IconName;
  /** Nombre completo para lectores de pantalla y tooltip cuando el rótulo es corto. */
  titulo?: string;
  /** Solo la ruta exacta la marca como actual (no sus subrutas). */
  exacta?: boolean;
  /** Otras rutas que también marcan esta entrada como actual. */
  tambien?: string[];
}

export interface GrupoNav {
  id: "diagnostico" | "plan" | "privacidad" | "documentos";
  titulo: string;
  /** Rótulo corto para la barra inferior (móvil). */
  corto: string;
  icono: IconName;
  entradas: EntradaNav[];
}

export const MI_EMPRESA: EntradaNav = { ruta: "/empresa", etiqueta: "Mi empresa", icono: "empresa", exacta: true };

/** Punto de entrada único del flujo mapa de datos → asistente → registro (Fase 8.B). */
export const RUTA_ARMA_REGISTRO = "/empresa/registro";

export function gruposNavegacion(modo: ModoNavegacion): GrupoNav[] {
  const cliente = modo === "cliente";
  const encuestado = modo === "encuestado";
  const grupos: GrupoNav[] = [
    {
      id: "diagnostico",
      titulo: "Diagnóstico",
      corto: "Diagnóstico",
      icono: "diagnostico",
      entradas: [
        { ruta: "/panel", etiqueta: "Resultados", titulo: "Resultados del diagnóstico", icono: "diagnostico", exacta: true },
        { ruta: "/panel/dominios", etiqueta: "Dominios", icono: "dominios" },
        // HU-10: comparativa contra el sector (k-anonimato)
        { ruta: "/panel/sector", etiqueta: "Sector", titulo: "Comparación con el sector", icono: "sector" },
        ...(cliente ? [{ ruta: "/empresa/evaluaciones", etiqueta: "Mis evaluaciones", icono: "historial" as const }] : []),
      ],
    },
    {
      id: "plan",
      titulo: "Plan de acción",
      corto: "Plan",
      icono: "brechas",
      entradas: [
        { ruta: "/panel/brechas", etiqueta: "Brechas", icono: "brechas" },
        // HU-26: /panel/capacitacion/[ruta] sigue marcando "Capacitación"
        { ruta: "/panel/capacitacion", etiqueta: "Capacitación", icono: "birrete" },
        // HU-17: cerrar brechas con evidencia (servicio contratado)
        ...(cliente ? [{ ruta: "/panel/remediacion", etiqueta: "Cerrar brechas", icono: "subir" as const }] : []),
      ],
    },
    {
      id: "privacidad",
      titulo: "Privacidad y registro",
      corto: "Privacidad",
      icono: "escudo",
      entradas: [
        ...(cliente
          ? [{
              ruta: RUTA_ARMA_REGISTRO,
              etiqueta: "Arma tu registro",
              titulo: "Arma tu registro de actividades: mapa de datos, asistente y registro",
              icono: "mapa" as const,
              tambien: ["/empresa/mapa-datos", "/empresa/registro-actividades"],
            }, {
              ruta: "/empresa/asistente",
              etiqueta: "Asistente",
              titulo: "Asistente de registro: pregunta y revisa tu registro",
              icono: "chispa" as const,
            }]
          : []),
        // HU-32: derechos ARCOP (cada titular tiene su página)
        ...(cliente || encuestado
          ? [{ ruta: cliente ? "/empresa/mis-derechos" : "/panel/mis-derechos", etiqueta: "Mis derechos", titulo: "Mis derechos sobre mis datos", icono: "escudo" as const }]
          : []),
      ],
    },
    {
      id: "documentos",
      titulo: "Documentos",
      corto: "Documentos",
      icono: "carpeta",
      entradas: [
        // HU-21: informe en PDF (gratis: también lo ve el encuestado)
        { ruta: "/panel/informe", etiqueta: "Informe", titulo: "Informe para el directorio", icono: "pdf" },
        // HU-16: borradores del aviso de privacidad y de la evaluación de impacto (servicio contratado)
        ...(cliente ? [{ ruta: "/empresa/borradores", etiqueta: "Borradores", titulo: "Borradores de documentos", icono: "documento" as const }] : []),
        ...(cliente ? [{ ruta: "/empresa/documentos", etiqueta: "Mis documentos", icono: "carpeta" as const }] : []),
      ],
    },
  ];
  return grupos.filter((g) => g.entradas.length > 0);
}

export function entradaActiva(e: EntradaNav, pathname: string): boolean {
  const coincide = (r: string, exacta?: boolean) => (exacta ? pathname === r : pathname === r || pathname.startsWith(`${r}/`));
  return coincide(e.ruta, e.exacta) || (e.tambien ?? []).some((r) => coincide(r));
}

export function grupoActivo(grupos: GrupoNav[], pathname: string): GrupoNav["id"] | null {
  return grupos.find((g) => g.entradas.some((e) => entradaActiva(e, pathname)))?.id ?? null;
}
