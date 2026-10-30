/**
 * HU-10 · Comparativa sectorial con k-anonimato: textos y cálculos de la vista.
 *
 * El backend ya suprime las métricas de cohortes con menos de k empresas. Aquí solo se
 * redacta lo que se muestra y se decide qué advertencia corresponde. Nada en esta capa debe
 * mostrar el número de empresas cuando la cohorte es insuficiente.
 */
import type { CodigoAdvertenciaSector, DominioVista, PosicionSector, SectorVista } from "./types";

/** Frase de posición, sin revelar puntajes de otras empresas. */
export const TEXTO_POSICION: Record<PosicionSector, string> = {
  bajo_cuartil_inferior: "Estás en el cuarto de empresas con menor madurez del sector.",
  franja_central: "Estás en la mitad central del sector.",
  sobre_cuartil_superior: "Estás en el cuarto de empresas con mayor madurez del sector.",
  bajo_promedio: "Estás bajo el promedio del sector.",
  en_promedio: "Estás en línea con el promedio del sector.",
  sobre_promedio: "Estás sobre el promedio del sector.",
};

/** Etiqueta corta para la columna de posición de cada dimensión. */
export const ETIQUETA_POSICION: Record<PosicionSector, string> = {
  bajo_cuartil_inferior: "Cuarto inferior",
  franja_central: "Mitad central",
  sobre_cuartil_superior: "Cuarto superior",
  bajo_promedio: "Bajo el promedio",
  en_promedio: "En el promedio",
  sobre_promedio: "Sobre el promedio",
};

export type TonoPosicion = "alto" | "medio" | "bajo";

export function tonoPosicion(p: PosicionSector | null): TonoPosicion | null {
  if (p == null) return null;
  if (p === "bajo_cuartil_inferior" || p === "bajo_promedio") return "alto";
  if (p === "sobre_cuartil_superior" || p === "sobre_promedio") return "bajo";
  return "medio";
}

/** Una posición entre 0 y 100 para dibujar (las marcas no se salen de la tira). */
export const enEscala = (v: number) => Math.min(100, Math.max(0, v));

export function formatoPuntos(n: number | null): string {
  if (n == null) return "—";
  const r = Math.round(n * 10) / 10;
  if (r === 0) return "Igual";
  const abs = Math.abs(r).toLocaleString("es-CL", { maximumFractionDigits: 1 });
  return `${r > 0 ? "+" : "−"}${abs} pts`;
}

/** ¿Qué advertencia mostrar? Si el backend es previo y no la trae, se deduce. */
export function advertenciaDe(s: SectorVista | null, sinRubro: boolean): CodigoAdvertenciaSector | null {
  if (s?.advertencia) return s.advertencia.codigo;
  if (sinRubro) return "SIN_RUBRO";
  if (s && !s.cohorteSuficiente) return "COHORTE_INSUFICIENTE";
  if (s && s.dimensionesSuprimidas > 0) return "COHORTE_PARCIAL";
  return null;
}

export interface TextoAviso {
  titulo: string;
  cuerpo: string;
  /** Aviso de privacidad (k < 5) frente a uno informativo. */
  tono: "aviso" | "info";
}

/** Textos de la advertencia (criterio 3). Nunca incluyen el número de empresas de la cohorte. */
export function textoAviso(codigo: CodigoAdvertenciaSector, k: number, s: SectorVista | null): TextoAviso {
  switch (codigo) {
    case "COHORTE_INSUFICIENTE":
      return {
        titulo: "Comparación sectorial oculta para proteger a las empresas",
        cuerpo:
          `Tu sector tiene menos de ${k} empresas evaluadas. Con un grupo tan pequeño, el promedio permitiría ` +
          `deducir el resultado de una empresa en particular, así que lo ocultamos. Aparecerá solo cuando ` +
          `${k} o más empresas de tu sector hayan completado la evaluación; mientras tanto, compárate con la meta.`,
        tono: "aviso",
      };
    case "COHORTE_PARCIAL": {
      const n = s?.dimensionesSuprimidas ?? 0;
      const total = (s?.dimensionesPublicadas ?? 0) + n;
      return {
        titulo: n === 1 ? "Una dimensión sin comparación sectorial" : `${n} dimensiones sin comparación sectorial`,
        cuerpo:
          `En ${n === 1 ? "1 dimensión" : `${n} dimensiones`} de ${total} hay menos de ${k} empresas con puntaje. ` +
          `Ocultamos esas comparaciones para que nadie pueda deducir resultados individuales.`,
        tono: "aviso",
      };
    }
    case "SIN_RUBRO":
    default:
      return {
        titulo: "Esta evaluación no tiene un sector asociado",
        cuerpo: "Por eso se compara solo con la meta de cumplimiento.",
        tono: "info",
      };
  }
}

/** Descripción de una tira para lectores de pantalla. */
export function describirTira(args: {
  nombre: string;
  puntaje: number;
  promedio: number | null;
  p25: number | null;
  p75: number | null;
  meta?: number | null;
  k: number;
}): string {
  const partes = [`${args.nombre}: tu empresa ${redondo(args.puntaje)} de 100`];
  if (args.promedio == null) {
    partes.push(`promedio del sector oculto, menos de ${args.k} empresas`);
  } else {
    partes.push(`promedio del sector ${args.promedio}`);
    if (args.p25 != null && args.p75 != null) partes.push(`mitad central del sector entre ${args.p25} y ${args.p75}`);
  }
  if (args.meta != null) partes.push(`meta ${redondo(args.meta)}`);
  return `${partes.join("; ")}.`;
}

const redondo = (n: number) => Math.round(n * 10) / 10;

/** Dimensiones ordenadas para comparar: primero las publicadas, de mayor a menor brecha bajo el sector. */
export function ordenarParaComparar(dominios: DominioVista[]): DominioVista[] {
  return [...dominios].sort((a, b) => {
    if (a.cohorteSuficiente !== b.cohorteSuficiente) return a.cohorteSuficiente ? -1 : 1;
    const da = a.diferencia ?? 0;
    const db = b.diferencia ?? 0;
    return da - db || a.nombre.localeCompare(b.nombre, "es");
  });
}
