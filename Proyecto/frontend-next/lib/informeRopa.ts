/**
 * Informe RoPA del registro de actividades (navegador → /bff/cliente/api/registro-actividades/ropa).
 *
 * El servidor arma el informe con la versión vigente de cada actividad, en dos partes según el rol marcado en
 * cada una (como responsable / como encargado), genera el PDF y el Excel con el mismo código, los guarda en
 * "Mis documentos" y deja cada guardado, emisión y descarga en el registro de auditoría.
 *
 * Aquí van las llamadas y la lógica pura de la pantalla (probada en tests/informe_ropa.test.ts):
 *   - qué falta para generar (la misma regla que app/domain/ropa/datos.py: el servidor vuelve a validarlo);
 *   - qué datos cambiaron (solo esos se envían al guardar).
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";
import { nombreDesdeDisposicion } from "@/lib/empresa";

export const BASE_ROPA = "/bff/cliente/api/registro-actividades/ropa";

export type ParteRopa = "responsable" | "encargado";
export type FormatoRopa = "pdf" | "xlsx";

export const PARTES: ParteRopa[] = ["responsable", "encargado"];
export const NOMBRE_PARTE: Record<ParteRopa, string> = { responsable: "Como responsable", encargado: "Como encargado" };

export interface TransferenciaRopa {
  destino: string;
  pais: string;
  garantia: string;
  con_garantia: boolean;
}

export interface ActividadRopa {
  id: number;
  numero: number;
  nombre: string;
  version: number | null;
  area: string | null;
  descripcion: string | null;
  finalidades: string[];
  titulares: string[];
  datos: string[];
  sensibles: boolean;
  destinatarios: string[];
  transferencias: TransferenciaRopa[];
  plazos: string[];
  /** { "Técnicas": [...], "Organizativas": [...], "Otras": [...] } */
  medidas: Record<string, string[]>;
  mandante: string | null;
}

export interface GrupoEncargado {
  clave: string;
  nombre: string;
  actividades: ActividadRopa[];
}

export interface PreviaRopa {
  partes: ParteRopa[];
  disponibles: ParteRopa[];
  responsable: ActividadRopa[];
  encargado: GrupoEncargado[];
  transferencias: (TransferenciaRopa & { actividad: string; rol: ParteRopa })[];
  resumen: { responsable: number; encargado: number; organizaciones: number; transferencias: number; transferencias_sin_garantia: number; excluidas: number };
  huella: string;
  aviso: { version: string; pie: string };
}

export interface MandanteDatos {
  clave: string;
  nombre: string;
  direccion: string | null;
  correo: string | null;
  dpo: string | null;
}

export interface DatosRopa {
  direccion: string | null;
  correo: string | null;
  telefono: string | null;
  tiene_dpo: boolean | null;
  dpo_cargo: string | null;
  dpo_correo: string | null;
  mandantes: MandanteDatos[];
}

export interface Faltante {
  /** "empresa" o la clave de la organización. */
  grupo: string;
  campo: string;
  mensaje: string;
}

export interface DocumentoEmision {
  id: number;
  nombre: string;
  tamano_bytes: number;
}

export interface EmisionRopa {
  id: number;
  codigo: string;
  version: number;
  fecha: string;
  partes: ParteRopa[];
  actividades: number;
  resumen: Partial<PreviaRopa["resumen"]>;
  aviso_version: string;
  documentos: { pdf: DocumentoEmision | null; xlsx: DocumentoEmision | null };
}

export interface ListaRopa {
  empresa: { razon_social: string; rut: string | null };
  previa: PreviaRopa;
  datos: DatosRopa;
  faltantes: Faltante[];
  faltantes_texto: string;
  puede_emitir: boolean;
  al_dia: boolean;
  version_siguiente: number;
  emisiones: EmisionRopa[];
}

export interface RespuestaEmisionRopa {
  informe: EmisionRopa;
  reutilizado: boolean;
  mensaje: string;
}

/* ============================================================ llamadas */

export const cargarRopa = () => pedir<ListaRopa>(BASE_ROPA);

export const guardarDatosRopa = (cambios: Partial<Omit<DatosRopa, "mandantes">> & { mandantes?: Omit<MandanteDatos, "nombre">[] }) =>
  pedir<{ datos: DatosRopa; faltantes: Faltante[]; faltantes_texto: string; guardado: boolean }>(`${BASE_ROPA}/datos`, {
    method: "PATCH",
    json: cambios,
  });

export const emitirRopa = (partes: ParteRopa[], forzar = false) =>
  pedir<RespuestaEmisionRopa>(BASE_ROPA, { method: "POST", json: { partes, forzar } });

export async function descargarRopa(id: number, formato: FormatoRopa): Promise<{ blob: Blob; nombre: string }> {
  const res = await fetch(`${BASE_ROPA}/${id}/descarga?formato=${formato}`, { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let info = { codigo: `HTTP_${res.status}`, mensaje: "" };
    try {
      info = ((await res.json()) as { error: typeof info }).error ?? info;
    } catch {
      /* sin cuerpo */
    }
    throw new ErrorBff(res.status, info);
  }
  return { blob: await res.blob(), nombre: nombreDesdeDisposicion(res.headers.get("content-disposition"), `ropa.${formato}`) };
}

/* ============================================================ lógica de la pantalla */

const EMAIL = /^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$/;
const TELEFONO = /^\+?[0-9][0-9 ()-]{5,22}$/;

/** Espacios simples y sin bordes; vacío → null (lo mismo que hace el servidor). */
export function limpio(v: string | null | undefined): string | null {
  const t = (v ?? "").split(/\s+/).filter(Boolean).join(" ");
  return t || null;
}

export const correoValido = (v: string | null | undefined) => !limpio(v) || EMAIL.test(limpio(v)!.toLowerCase());
export const telefonoValido = (v: string | null | undefined) => !limpio(v) || TELEFONO.test(limpio(v)!);

/** Qué falta para generar las partes elegidas (misma regla que el servidor). */
export function faltantes(d: DatosRopa, partes: ParteRopa[]): Faltante[] {
  const salida: Faltante[] = [];
  const falta = (grupo: string, campo: string, mensaje: string) => salida.push({ grupo, campo, mensaje });
  if (!limpio(d.direccion)) falta("empresa", "direccion", "Escribe la dirección de tu empresa.");
  if (!limpio(d.correo)) falta("empresa", "correo", "Escribe el correo de contacto de tu empresa.");
  if (d.tiene_dpo === null) falta("empresa", "tiene_dpo", "Indica si tu empresa tiene delegado de protección de datos.");
  else if (d.tiene_dpo) {
    if (!limpio(d.dpo_cargo)) falta("empresa", "dpo_cargo", "Escribe el cargo o el área del delegado de protección de datos.");
    if (!limpio(d.dpo_correo)) falta("empresa", "dpo_correo", "Escribe el correo del delegado de protección de datos.");
  }
  if (partes.includes("encargado")) {
    for (const m of d.mandantes) {
      if (!limpio(m.direccion)) falta(m.clave, "direccion", `Escribe la dirección de ${m.nombre}.`);
      if (!limpio(m.correo)) falta(m.clave, "correo", `Escribe el correo de contacto de ${m.nombre}.`);
    }
  }
  return salida;
}

/** Formatos que el servidor rechazaría (correo o teléfono mal escritos), con el mismo grupo/campo. */
export function erroresFormato(d: DatosRopa, partes: ParteRopa[]): Faltante[] {
  const salida: Faltante[] = [];
  if (!correoValido(d.correo)) salida.push({ grupo: "empresa", campo: "correo", mensaje: "Revisa el formato del correo de tu empresa." });
  if (!telefonoValido(d.telefono)) salida.push({ grupo: "empresa", campo: "telefono", mensaje: "Revisa el teléfono: solo números, espacios, guiones y +." });
  if (d.tiene_dpo && !correoValido(d.dpo_correo)) salida.push({ grupo: "empresa", campo: "dpo_correo", mensaje: "Revisa el formato del correo del delegado." });
  if (d.tiene_dpo && limpio(d.dpo_cargo)?.includes("@")) salida.push({ grupo: "empresa", campo: "dpo_cargo", mensaje: "Indica el cargo o el área del delegado, sin correos." });
  if (partes.includes("encargado")) {
    for (const m of d.mandantes) {
      if (!correoValido(m.correo)) salida.push({ grupo: m.clave, campo: "correo", mensaje: `Revisa el formato del correo de ${m.nombre}.` });
    }
  }
  return salida;
}

/** «Completa los datos de la empresa y Grupo Sur S.A.» */
export function textoFaltantes(lista: Faltante[], d: DatosRopa): string {
  const grupos: string[] = [];
  for (const f of lista) {
    const nombre = f.grupo === "empresa" ? "los datos de la empresa" : d.mandantes.find((m) => m.clave === f.grupo)?.nombre ?? f.grupo;
    if (!grupos.includes(nombre)) grupos.push(nombre);
  }
  if (!grupos.length) return "";
  const texto = "Completa " + (grupos.length === 1 ? grupos[0] : `${grupos.slice(0, -1).join(", ")} y ${grupos[grupos.length - 1]}`);
  return texto.endsWith(".") ? texto : `${texto}.`;
}

const CAMPOS_EMPRESA = ["direccion", "correo", "telefono", "tiene_dpo", "dpo_cargo", "dpo_correo"] as const;

/** Solo lo que cambió respecto de lo guardado (null si no hay nada que guardar). */
export function cambiosDatos(antes: DatosRopa, ahora: DatosRopa): Parameters<typeof guardarDatosRopa>[0] | null {
  const cambios: Record<string, unknown> = {};
  for (const k of CAMPOS_EMPRESA) {
    const a = k === "tiene_dpo" ? antes[k] : limpio(antes[k] as string | null);
    const b = k === "tiene_dpo" ? ahora[k] : limpio(ahora[k] as string | null);
    if (a !== b) cambios[k] = b;
  }
  const mandantes = ahora.mandantes
    .filter((m) => {
      const previo = antes.mandantes.find((x) => x.clave === m.clave);
      return !previo || (["direccion", "correo", "dpo"] as const).some((k) => limpio(previo[k]) !== limpio(m[k]));
    })
    .map((m) => ({ clave: m.clave, direccion: limpio(m.direccion), correo: limpio(m.correo), dpo: limpio(m.dpo) }));
  if (mandantes.length) cambios.mandantes = mandantes;
  return Object.keys(cambios).length ? (cambios as Parameters<typeof guardarDatosRopa>[0]) : null;
}

/** Texto de las partes que trae una emisión. */
export function textoPartes(partes: ParteRopa[]): string {
  if (partes.length === 2) return "Responsable y encargado";
  return partes[0] === "encargado" ? "Encargado" : partes[0] === "responsable" ? "Responsable" : "—";
}
