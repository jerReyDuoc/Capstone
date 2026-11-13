/**
 * Revisión interna del registro (navegador → /bff/cliente/api/registro-actividades/revision).
 *
 * El mismo usuario de la empresa revisa el registro y el mapa de datos con una lista de verificación, deja
 * observaciones, las cierra al corregir y marca la versión del registro como revisada. El servidor calcula los
 * resultados, guarda lo decidido y deja todo en el registro de auditoría. Aquí van las llamadas y la lógica pura
 * de presentación (probada en tests/revision_interna.test.ts).
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import { nombreDesdeDisposicion } from "@/lib/empresa";

export const BASE_REVISION = "/bff/cliente/api/registro-actividades/revision";

/* ============================================================ tipos */

export type Resultado = "cumple" | "advertencia" | "falla" | "no_aplica";
export type EstadoPunto = "pendiente" | "verificado" | "aceptado" | "desactualizado" | "no_aplica";
export type Decision = "verificado" | "aceptado" | "pendiente";
export type TipoObjeto = "actividad" | "elemento" | "flujo";
export type Prioridad = "alta" | "media" | "baja";
export type EstadoPeriodo = "al_dia" | "por_vencer" | "vencida" | "sin_revision" | "sin_registro";

export interface Punto {
  codigo: string;
  titulo: string;
  resultado: Resultado;
  detalle: string;
  bloqueante: boolean;
  revision: EstadoPunto;
  nota: string | null;
  fecha_revision: string | null;
}

export interface ObjetoRevision {
  clave: string;
  tipo: TipoObjeto;
  id: number;
  nombre: string;
  subtitulo: string;
  huella: string;
  items: Punto[];
  revisados: number;
  por_revisar: number;
  completo: boolean;
  fallas: number;
  advertencias: number;
  bloqueos: number;
}

export interface Observacion {
  id: number;
  numero: number;
  revision_id: number;
  objeto_tipo: TipoObjeto | "registro";
  objeto_id: number | null;
  objeto_clave: string;
  objeto_nombre: string;
  objeto_existe: boolean;
  criterio: string | null;
  criterio_titulo: string | null;
  prioridad: Prioridad;
  texto: string;
  estado: "abierta" | "cerrada";
  fecha_apertura: string;
  fecha_cierre: string | null;
  nota_cierre: string | null;
  objeto_cambio: boolean | null;
  reaperturas: number;
  cambio_desde_apertura: boolean | null;
}

export interface ResumenRevision {
  objetos: number;
  por_tipo: Record<TipoObjeto, number>;
  puntos: number;
  revisados: number;
  verificados: number;
  aceptados: number;
  pendientes: number;
  desactualizados: number;
  por_resultado: Record<Resultado, number>;
  objetos_completos: number;
  observaciones: { total: number; abiertas: number; cerradas: number; por_prioridad: Record<Prioridad, number> };
  porcentaje: number;
}

export interface Revision {
  id: number;
  numero: number;
  estado: "en_curso" | "revisada";
  fecha_inicio: string;
  fecha_revision: string | null;
  revisor: string | null;
  cargo: string | null;
  conclusion: string | null;
  version_rat: number | null;
  huella: string | null;
  huella_legible: string | null;
  version_mapa: number | null;
  resumen: Partial<ResumenRevision>;
  informe_id: number | null;
}

export interface Criterio {
  codigo: string;
  titulo: string;
  pregunta: string;
  bloqueante: boolean;
}

export interface Periodicidad {
  estado: EstadoPeriodo;
  vence: string | null;
  dias: number | null;
  base: "ultima_revision" | "primera_vigencia" | null;
  plazo_meses: number;
  aviso_dias: number;
  recordatorio_correo: boolean;
  ultimo_recordatorio: string | null;
  personalizada: boolean;
  ultima_revision: string | null;
}

export interface VersionRegistro {
  version: number;
  fecha: string | null;
  borrador: boolean;
  codigo: string | null;
  actividades: number;
  revisada: boolean;
  revision: { numero: number; fecha: string | null } | null;
}

export interface Marca {
  id: number;
  numero: number;
  fecha: string;
  revisor: string;
  cargo: string | null;
  version_rat: number;
  texto: string;
}

export interface EstadoRevision {
  revision: Revision | null;
  registro: {
    huella: string;
    huella_legible: string;
    borrador: boolean;
    motivos_borrador: string[];
    actividades: number;
    version_mapa: number;
    version_siguiente: number;
    revisada: Marca | null;
    cambio_desde_ultima: boolean;
  };
  objetos: ObjetoRevision[];
  observaciones: Observacion[];
  resumen: ResumenRevision;
  requisitos: { puede_marcar: boolean; faltan: { codigo: string; texto: string; cantidad?: number }[] };
  criterios: Record<TipoObjeto, Criterio[]>;
  periodicidad: Periodicidad;
  revisadas: Revision[];
  ultima: Revision | null;
  versiones: VersionRegistro[];
  limites: { paquetes_dia: number; correos_dia: number; paquete_correo_mb: number; paquete_verificar_mb: number };
  correo_habilitado: boolean;
  revisor_sugerido: string;
}

export interface CambioCampo {
  codigo: string;
  titulo: string;
  antes: string;
  despues: string;
}

export interface Diferencias {
  desde: number;
  hasta: number | null;
  etiqueta: string;
  agregadas: { id: number; nombre: string; version: number | null }[];
  quitadas: { id: number; nombre: string; version: number | null }[];
  cambiadas: { id: number; nombre: string; version_antes: number | null; version_despues: number | null; campos: CambioCampo[] }[];
  iguales: { id: number; nombre: string; version: number | null }[];
  sin_cambios: boolean;
  totales: { agregadas: number; quitadas: number; cambiadas: number; iguales: number };
}

export interface ResultadoVerificacionPaquete {
  valido: boolean;
  registrado: boolean;
  integro: boolean;
  sha256: string;
  alterados: string[];
  faltantes: string[];
  sobrantes: string[];
  mensaje: string;
  paquete: { codigo: string; fecha: string; archivos: number; revision: { numero: number; estado: string; version_rat: number | null } | null } | null;
}

/* ============================================================ llamadas */

export const cargarRevision = () => pedir<EstadoRevision>(BASE_REVISION);
export const iniciarRevision = () => pedir<EstadoRevision & { mensaje: string }>(BASE_REVISION, { method: "POST" });

export const decidir = (clave: string, decision: Decision, criterios?: string[], nota?: string) =>
  pedir<{ objeto: ObjetoRevision; mensaje: string }>(`${BASE_REVISION}/verificaciones`, {
    method: "POST",
    json: { clave, decision, ...(criterios?.length ? { criterios } : {}), ...(nota?.trim() ? { nota: nota.trim() } : {}) },
  });

export const observar = (clave: string, prioridad: Prioridad, texto: string, criterio?: string | null) =>
  pedir<{ observacion: Observacion; mensaje: string }>(`${BASE_REVISION}/observaciones`, {
    method: "POST",
    json: { clave, prioridad, texto: texto.trim(), ...(criterio ? { criterio } : {}) },
  });

export const cerrarObservacion = (id: number, nota: string) =>
  pedir<{ observacion: Observacion; mensaje: string }>(`${BASE_REVISION}/observaciones/${id}/cerrar`, {
    method: "POST",
    json: { nota: nota.trim() },
  });

export const reabrirObservacion = (id: number) =>
  pedir<{ observacion: Observacion; mensaje: string }>(`${BASE_REVISION}/observaciones/${id}/reabrir`, { method: "POST" });

export const marcarRevisada = (datos: { revisor_nombre: string; revisor_cargo?: string; conclusion?: string; huella: string }) =>
  pedir<{ revision: Revision; informe: { id: number; codigo: string; version_rat: number } | null; mensaje: string }>(
    `${BASE_REVISION}/marcar`,
    {
      method: "POST",
      json: {
        revisor_nombre: datos.revisor_nombre.trim(),
        ...(datos.revisor_cargo?.trim() ? { revisor_cargo: datos.revisor_cargo.trim() } : {}),
        ...(datos.conclusion?.trim() ? { conclusion: datos.conclusion.trim() } : {}),
        huella: datos.huella,
        confirmo: true,
      },
    },
  );

export const cargarDiferencias = (desde: number | null, hasta: number | null) => {
  const q = new URLSearchParams();
  if (desde) q.set("desde", String(desde));
  if (hasta) q.set("hasta", String(hasta));
  const s = q.toString();
  return pedir<Diferencias>(`${BASE_REVISION}/diferencias${s ? `?${s}` : ""}`);
};

export const guardarPeriodicidad = (plazo_meses: number, aviso_dias: number, recordatorio_correo: boolean) =>
  pedir<{ periodicidad: Periodicidad; mensaje: string }>(`${BASE_REVISION}/configuracion`, {
    method: "PATCH",
    json: { plazo_meses, aviso_dias, recordatorio_correo },
  });

export const enviarRevision = (id: number, email: string, conPaquete: boolean) =>
  pedir<{ enviado: boolean; destino: string; modo: string; con_paquete: boolean }>(`${BASE_REVISION}/revisiones/${id}/enviar`, {
    method: "POST",
    json: { ...(email.trim() ? { email: email.trim() } : {}), con_paquete: conPaquete },
  });

async function binario(url: string, respaldo: string): Promise<{ blob: Blob; nombre: string; codigo: string | null }> {
  const res = await fetch(url, { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let info = { codigo: `HTTP_${res.status}`, mensaje: "" };
    try {
      info = ((await res.json()) as { error: typeof info }).error ?? info;
    } catch {
      /* sin cuerpo */
    }
    throw new ErrorBff(res.status, info);
  }
  return {
    blob: await res.blob(),
    nombre: nombreDesdeDisposicion(res.headers.get("content-disposition"), respaldo),
    codigo: res.headers.get("x-paquete-codigo"),
  };
}

export const descargarConstancia = (id: number) =>
  binario(`${BASE_REVISION}/revisiones/${id}/constancia`, `revision_interna_${id}.pdf`);

export const descargarPaquete = (id: number) =>
  binario(`${BASE_REVISION}/revisiones/${id}/paquete`, `paquete_revision_${id}.zip`);

export async function verificarPaquete(archivo: File): Promise<ResultadoVerificacionPaquete> {
  const datos = new FormData();
  datos.append("file", archivo);
  return pedir<ResultadoVerificacionPaquete>(`${BASE_REVISION}/paquetes/verificacion`, { method: "POST", body: datos });
}

/* ============================================================ presentación (lógica pura) */

export const TITULO_RESULTADO: Record<Resultado, string> = {
  cumple: "Cumple",
  advertencia: "Advertencia",
  falla: "Falla",
  no_aplica: "No aplica",
};

export const TONO_RESULTADO: Record<Resultado, string> = {
  cumple: "tone-ok",
  advertencia: "tone-medio",
  falla: "tone-critico",
  no_aplica: "tone-bajo",
};

export const TITULO_PUNTO: Record<EstadoPunto, string> = {
  pendiente: "Por revisar",
  verificado: "Verificado",
  aceptado: "Aceptado con justificación",
  desactualizado: "Cambió: revísalo de nuevo",
  no_aplica: "No aplica",
};

export const TITULO_TIPO: Record<TipoObjeto | "registro", string> = {
  actividad: "Actividad",
  elemento: "Elemento del mapa",
  flujo: "Flujo del mapa",
  registro: "Registro completo",
};

export const TITULO_PRIORIDAD: Record<Prioridad, string> = { alta: "Alta", media: "Media", baja: "Baja" };
export const TONO_PRIORIDAD: Record<Prioridad, string> = { alta: "tone-critico", media: "tone-medio", baja: "tone-info" };

export type FiltroTipo = "todos" | TipoObjeto;
export type FiltroAvance = "todos" | "pendientes" | "con_fallas" | "completos";

/** Lo que se ve de la lista: por tipo, por avance y por nombre (sin distinguir tildes ni mayúsculas). */
export function filtrarObjetos(objs: ObjetoRevision[], tipo: FiltroTipo, avance: FiltroAvance, busqueda: string): ObjetoRevision[] {
  const q = normalizar(busqueda);
  return objs.filter(
    (o) =>
      (tipo === "todos" || o.tipo === tipo) &&
      (avance === "todos" ||
        (avance === "pendientes" && !o.completo) ||
        (avance === "con_fallas" && o.fallas > 0) ||
        (avance === "completos" && o.completo)) &&
      (!q || normalizar(`${o.nombre} ${o.subtitulo}`).includes(q)),
  );
}

export function normalizar(t: string): string {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/** ¿Qué acciones tiene un punto? (las mismas reglas que valida el servidor). */
export function accionesPunto(p: Punto): { verificar: boolean; aceptar: boolean; deshacer: boolean } {
  if (p.resultado === "no_aplica") return { verificar: false, aceptar: false, deshacer: false };
  const decidido = p.revision === "verificado" || p.revision === "aceptado";
  return {
    verificar: !decidido && p.resultado !== "falla",
    aceptar: !decidido && p.resultado !== "cumple" && !(p.bloqueante && p.resultado === "falla"),
    deshacer: decidido,
  };
}

/** Puntos que se pueden verificar de una vez (los que cumplen o tienen advertencia y siguen pendientes). */
export function verificablesDeUnaVez(o: ObjetoRevision): number {
  return o.items.filter((p) => p.resultado !== "falla" && p.resultado !== "no_aplica" && (p.revision === "pendiente" || p.revision === "desactualizado")).length;
}

/** Dónde se corrige cada cosa: la actividad (en su paso) o el mapa de datos. */
export function enlaceCorregir(o: Pick<ObjetoRevision, "tipo" | "id">, criterio?: string): { href: string; texto: string } {
  if (o.tipo !== "actividad") return { href: "/empresa/mapa-datos", texto: "Corregir en el mapa de datos" };
  const paso = { campos: 1, base_licitud: 3, transferencias: 4, terceros: 4, plazos: 5, decisiones: 5 }[criterio ?? ""];
  if (criterio === "transferencias" || criterio === "terceros") {
    return { href: "/empresa/mapa-datos", texto: "Corregir en el mapa de datos" };
  }
  return { href: `/empresa/registro-actividades?actividad=${o.id}${paso ? `&paso=${paso}` : ""}`, texto: "Abrir la actividad" };
}

/** Texto y tono del estado de la revisión periódica. */
export function textoPeriodicidad(p: Periodicidad): { titulo: string; detalle: string; tono: "ok" | "aviso" | "alerta" | "info" } {
  const vence = p.vence ? fechaCorta(p.vence) : "";
  switch (p.estado) {
    case "vencida":
      return {
        tono: "alerta",
        titulo: "La revisión periódica está vencida",
        detalle: `Venció el ${vence} (${Math.abs(p.dias ?? 0)} día(s) atrás). Revisa el registro para dejar constancia de que sigue al día.`,
      };
    case "por_vencer":
      return {
        tono: "aviso",
        titulo: "La revisión periódica vence pronto",
        detalle: `Vence el ${vence}, en ${p.dias} día(s). Revisa el registro antes de esa fecha.`,
      };
    case "al_dia":
      return { tono: "ok", titulo: "Revisión al día", detalle: `La próxima revisión vence el ${vence} (cada ${p.plazo_meses} meses).` };
    case "sin_revision":
      return {
        tono: "info",
        titulo: "Aún no haces la primera revisión interna",
        detalle: `Hazla antes del ${vence} para cumplir el plazo de ${p.plazo_meses} meses desde que el registro quedó vigente.`,
      };
    default:
      return { tono: "info", titulo: "Todavía no hay nada que revisar", detalle: "Deja vigente al menos una actividad del registro." };
  }
}

/** "2027-11-13" → "13-11-2027". */
export function fechaCorta(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}-${m[2]}-${m[1]}` : iso;
}

/** Agrupa las observaciones: primero las abiertas por prioridad, luego las cerradas más recientes. */
export function ordenarObservaciones(lista: Observacion[]): Observacion[] {
  const peso: Record<Prioridad, number> = { alta: 0, media: 1, baja: 2 };
  return [...lista].sort((a, b) => {
    if (a.estado !== b.estado) return a.estado === "abierta" ? -1 : 1;
    if (a.estado === "abierta") return peso[a.prioridad] - peso[b.prioridad] || a.numero - b.numero;
    return (b.fecha_cierre ?? "").localeCompare(a.fecha_cierre ?? "");
  });
}

/** Problema de un nombre de quien revisa (o null): letras, 2 a 120 caracteres, sin números ni correos. */
export function problemaNombre(nombre: string): string | null {
  const v = nombre.trim();
  if (!v) return "Escribe el nombre de quien revisa.";
  if (v.length < 2 || v.length > 120) return "Usa entre 2 y 120 caracteres.";
  if (!/^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .,\-()/]+$/.test(v)) return "Usa solo letras, sin números ni correos.";
  return null;
}
