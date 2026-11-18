/**
 * Auditoría UX 16-11 · Fase 8.C: "Mi empresa" como tablero de PRÓXIMOS PASOS.
 *
 * Arma, con los datos que el frontend ya recibe, la lista de lo accionable ordenada por urgencia:
 * vencimientos próximos, propuestas por revisar, brechas críticas abiertas y el estado real del
 * registro de actividades. Lógica pura (probada en tests/tablero_empresa.test.ts).
 */
import { RUTA_ARMA_REGISTRO } from "./navegacion";

export type TonoPaso = "urgente" | "atencion" | "info" | "ok";

export interface PasoTablero {
  id: string;
  tono: TonoPaso;
  titulo: string;
  detalle: string;
  accion: { texto: string; href: string };
}

export interface EntradaTablero {
  /** Días para el término del contrato (negativo = terminó). */
  diasContrato: number | null;
  fechaTerminoContrato?: string;
  /** Revisión interna periódica del registro. */
  revision?: { estado: "al_dia" | "por_vencer" | "vencida" | "sin_revision" | "sin_registro"; dias: number | null } | null;
  /** Actividades del registro propuestas por el asistente que esperan revisión. */
  porRevisar: number | null;
  /** Brechas críticas abiertas de la evaluación más reciente. */
  brechasCriticas: number | null;
  /** Estado del mapa y del registro. */
  registro: { mapaIniciado: boolean; activas: number; vigenteCompleto: boolean; evidenciaAplicable: boolean } | null;
}

const PESO: Record<TonoPaso, number> = { urgente: 0, atencion: 1, info: 2, ok: 3 };

/** Estado del registro en palabras (lo que se muestra en el tablero). */
export function estadoRegistro(r: NonNullable<EntradaTablero["registro"]>): { titulo: string; detalle: string; tono: TonoPaso; accion: string } {
  if (!r.mapaIniciado && r.activas === 0) {
    return { titulo: "Registro de actividades: sin empezar", detalle: "Parte por el mapa de datos: qué datos tratas y dónde están.", tono: "atencion", accion: "Empezar" };
  }
  if (r.activas === 0) {
    return { titulo: "Tu mapa está listo", detalle: "Ahora registra las actividades en que usas esos datos.", tono: "atencion", accion: "Continuar" };
  }
  if (!r.vigenteCompleto) {
    return {
      titulo: "El registro aún no respalda controles",
      detalle: "Completa y deja vigentes tus actividades para que cuenten como evidencia en tu evaluación.",
      tono: "info",
      accion: "Continuar",
    };
  }
  return {
    titulo: "Registro vigente y completo",
    detalle: r.evidenciaAplicable ? "Ya puedes usarlo como evidencia en tu evaluación." : "Mantenlo al día con la revisión periódica.",
    tono: "ok",
    accion: "Ver registro",
  };
}

export function proximosPasos(e: EntradaTablero): PasoTablero[] {
  const pasos: PasoTablero[] = [];

  if (e.diasContrato != null && e.diasContrato <= 60) {
    pasos.push({
      id: "contrato",
      tono: e.diasContrato <= 15 ? "urgente" : "atencion",
      titulo: e.diasContrato < 0 ? "El contrato de tu empresa terminó" : `El contrato termina en ${e.diasContrato} ${e.diasContrato === 1 ? "día" : "días"}`,
      detalle: "Contacta a Therion Labs para renovarlo y no perder el acceso al servicio.",
      accion: { texto: "Ver contrato", href: "/empresa/configuracion" },
    });
  }

  if (e.revision && (e.revision.estado === "vencida" || e.revision.estado === "por_vencer")) {
    const vencida = e.revision.estado === "vencida";
    pasos.push({
      id: "revision",
      tono: vencida ? "urgente" : "atencion",
      titulo: vencida ? "La revisión interna del registro está vencida" : `La revisión interna vence en ${e.revision.dias ?? 0} días`,
      detalle: "Revisa el registro y deja constancia de la revisión.",
      accion: { texto: "Revisar el registro", href: "/empresa/registro-actividades/revision" },
    });
  }

  if (e.porRevisar) {
    pasos.push({
      id: "propuestas",
      tono: "atencion",
      titulo: `${e.porRevisar} ${e.porRevisar === 1 ? "propuesta pendiente" : "propuestas pendientes"} de revisar`,
      detalle: "El asistente dejó actividades listas para que las revises y las aceptes o corrijas.",
      accion: { texto: "Revisar propuestas", href: "/empresa/registro-actividades" },
    });
  }

  if (e.brechasCriticas) {
    pasos.push({
      id: "criticas",
      tono: "urgente",
      titulo: `${e.brechasCriticas} ${e.brechasCriticas === 1 ? "brecha crítica abierta" : "brechas críticas abiertas"}`,
      detalle: "Son las que conviene atender primero: cada una trae la acción sugerida y su ruta formativa.",
      accion: { texto: "Ver brechas críticas", href: "/panel/brechas?severidad=Cr%C3%ADtica" },
    });
  }

  if (e.registro) {
    const r = estadoRegistro(e.registro);
    pasos.push({ id: "registro", tono: r.tono, titulo: r.titulo, detalle: r.detalle, accion: { texto: r.accion, href: RUTA_ARMA_REGISTRO } });
  }

  return pasos.sort((a, b) => PESO[a.tono] - PESO[b.tono]);
}
