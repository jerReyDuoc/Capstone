/**
 * HU-41 · "Privacidad de la plataforma" del panel interno (navegador → /bff/admin/api/admin/privacidad-plataforma).
 * Los tipos reflejan app/api/routes/admin_privacidad.py. Aquí solo hay llamadas y textos de pantalla (lógica pura,
 * probada en tests/privacidad_plataforma.test.ts): el registro lo genera el backend desde el inventario de datos.
 */
import { ErrorBff, pedir } from "@/lib/encuesta/cliente";

export type NivelHallazgo = "critico" | "alto" | "medio" | "bajo";
export type EstadoRevision = "ok" | "alerta" | "error";
export type TipoInforme = "rat" | "ropa";

export interface Hallazgo {
  codigo: string;
  nivel: NivelHallazgo;
  titulo: string;
  detalle: string;
  recomendacion: string;
  actividades: string[];
  /** Nombre técnico del ajuste que lo resuelve (solo para el equipo). */
  ajuste: string | null;
}

export interface Revision {
  codigo: string;
  estado: EstadoRevision;
  titulo: string;
  detalle: string;
}

export interface Proveedor {
  clave: string;
  nombre: string;
  descripcion: string;
  pais: string | null;
  pais_nombre: string | null;
  rol: "encargado";
  rol_nombre: string;
  garantia: string | null;
  garantia_nombre: string | null;
  garantia_valida: boolean;
  contrato_confirmado: boolean;
}

export interface PlazoActividad {
  categoria: string;
  categoria_nombre: string;
  dias: number | null;
  ajuste: string | null;
  ajustes: string[];
  desactivados: string[];
  sin_numero: string[];
  fundamento: string;
  /** "180 días desde que se cumple la finalidad" o "Sin plazo definido". */
  texto: string;
}

export interface Transferencia {
  flujo_id: number;
  nombre: string;
  pais_destino: string;
  pais_nombre: string;
  garantia: string | null;
  garantia_nombre: string;
  garantia_valida: boolean;
}

export interface Actividad {
  clave: string;
  numero: number;
  nombre: string;
  area: string;
  descripcion: string;
  tablas: string[];
  finalidades: string[];
  base_licitud: string;
  base_nombre: string;
  rol: string;
  rol_nombre: string;
  fuentes: string[];
  titulares: string[];
  datos: string[];
  plazos: PlazoActividad[];
  proveedores: Proveedor[];
  transferencias: Transferencia[];
  medidas: Record<string, string[]>;
  decisiones: string;
  completa: boolean;
  porcentaje: number;
  faltantes: string[];
  advertencias: string[];
}

export interface ElementoMapa {
  id: number;
  clave: string;
  tipo: "sistema" | "base_datos" | "tercero";
  tipo_nombre: string;
  subtipo_nombre: string;
  nombre: string;
  descripcion: string | null;
  proveedor: string | null;
  pais: string | null;
  pais_nombre: string | null;
  categorias: string[];
  actividades: string[];
}

export interface FlujoMapa {
  id: number;
  origen_id: number;
  destino_id: number;
  destino: string;
  categorias: string[];
  internacional: boolean;
  pais_destino: string | null;
  garantia: string | null;
  garantia_nombre: string | null;
  garantia_valida: boolean;
}

export interface AjustePlazo {
  clave: string;
  nombre: string;
  dias: number | null;
  fuente: "panel" | "entorno";
  fuente_texto: string;
  activo: boolean;
}

export interface Emision {
  id: number;
  tipo: TipoInforme;
  tipo_nombre: string;
  codigo: string;
  version: number;
  fecha: string;
  oficial: boolean;
  motivos_borrador: string[];
  actividades: number;
  huella_legible: string;
  resumen: Record<string, unknown>;
  aviso_version: string;
  archivos: { pdf: { nombre: string }; xlsx: { nombre: string } };
}

export interface DatosRopa {
  direccion: string | null;
  correo: string | null;
  telefono: string | null;
  tiene_dpo: boolean | null;
  dpo_cargo: string | null;
  dpo_correo: string | null;
}

export interface FaltanteRopa {
  grupo: string;
  campo: keyof DatosRopa;
  mensaje: string;
}

export interface EstadoRopa {
  datos: DatosRopa;
  faltantes: FaltanteRopa[];
  texto_faltantes: string;
  puede_emitir: boolean;
  al_dia?: boolean;
  cambio_desde_ultima?: boolean;
  version_siguiente?: number;
}

export interface ResumenPrivacidad {
  organizacion: { razon_social: string; rut: string | null };
  registro: {
    huella: string;
    huella_legible: string;
    oficial: boolean;
    motivos_borrador: string[];
    version_siguiente: number;
    al_dia: boolean;
    cambio_desde_ultima: boolean;
    pais_alojamiento: string;
    pais_alojamiento_nombre: string;
  };
  resumen: {
    actividades: number;
    transferencias: number;
    transferencias_sin_garantia: number;
    terceros: number;
    terceros_sin_contrato: number;
    riesgos_altos: number;
    [k: string]: unknown;
  };
  actividades: Actividad[];
  mapa: { elementos: ElementoMapa[]; flujos: FlujoMapa[]; resumen: Record<string, unknown> };
  proveedores: Proveedor[];
  ajustes: AjustePlazo[];
  revision: { revisiones: Revision[]; hallazgos: Hallazgo[]; conteo: Record<NivelHallazgo, number> };
  ropa: EstadoRopa & { al_dia: boolean; cambio_desde_ultima: boolean; version_siguiente: number };
  ultimas: Record<TipoInforme, Emision | null>;
  emisiones: Emision[];
  limites: { informes_dia: number };
}

export interface ResultadoEmision {
  informe: Emision;
  reutilizado: boolean;
  mensaje: string;
}

export interface ResultadoVerificacion {
  valido: boolean;
  informe: Emision;
  sigue_al_dia: boolean;
  mensaje: string;
}

const BASE = "/bff/admin/api/admin/privacidad-plataforma";

export const apiPrivacidad = {
  resumen: () => pedir<ResumenPrivacidad>(BASE),
  guardarRopa: (cambios: Partial<DatosRopa>) =>
    pedir<EstadoRopa & { cambiados: string[] }>(`${BASE}/ropa-datos`, { method: "PATCH", json: cambios }),
  emitir: (tipo: TipoInforme, forzar = false) =>
    pedir<ResultadoEmision>(`${BASE}/informes`, { method: "POST", json: { tipo, forzar } }),
  verificar: (codigo: string) =>
    pedir<ResultadoVerificacion>(`${BASE}/informes/verificacion?codigo=${encodeURIComponent(codigo.trim())}`),
  urlDescarga: (id: number, formato: "pdf" | "xlsx") => `${BASE}/informes/${id}/descarga?formato=${formato}`,
  urlMapa: () => `${BASE}/mapa/descarga`,
};

/** Descarga un archivo del panel (PDF o Excel) y lo guarda con el nombre que propone el servidor. */
export async function descargarArchivo(url: string, respaldo: string): Promise<void> {
  const res = await fetch(url, { credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let info = { codigo: `HTTP_${res.status}`, mensaje: "" };
    try {
      const cuerpo = (await res.json()) as { error?: { codigo: string; mensaje: string } };
      if (cuerpo?.error?.codigo) info = cuerpo.error;
    } catch {
      /* sin cuerpo */
    }
    throw new ErrorBff(res.status, info);
  }
  const blob = await res.blob();
  const enlace = document.createElement("a");
  enlace.href = URL.createObjectURL(blob);
  enlace.download = nombreDesdeDisposicion(res.headers.get("content-disposition"), respaldo);
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(enlace.href), 1000);
}

/** attachment; filename="registro_plataforma_v2_2026-11-13.pdf" → el nombre (solo [A-Za-z0-9_.-]). */
export function nombreDesdeDisposicion(cabecera: string | null, respaldo: string): string {
  const m = /filename="([\w.-]+)"/.exec(cabecera ?? "");
  return m ? m[1] : respaldo;
}

export const NIVEL_HALLAZGO: Record<NivelHallazgo, { texto: string; tono: string }> = {
  critico: { texto: "Crítico", tono: "tone-critico" },
  alto: { texto: "Alto", tono: "tone-alto" },
  medio: { texto: "Medio", tono: "tone-medio" },
  bajo: { texto: "Informativo", tono: "tone-info" },
};

export type FiltroNivel = "todos" | NivelHallazgo;

export function filtrarHallazgos(lista: Hallazgo[], filtro: FiltroNivel): Hallazgo[] {
  return filtro === "todos" ? lista : lista.filter((h) => h.nivel === filtro);
}

/** "1 alto · 4 medios" (sin los niveles en cero). */
export function resumenHallazgos(conteo: Partial<Record<NivelHallazgo, number>>): string {
  const nombres: Record<NivelHallazgo, [string, string]> = {
    critico: ["crítico", "críticos"],
    alto: ["alto", "altos"],
    medio: ["medio", "medios"],
    bajo: ["informativo", "informativos"],
  };
  const partes = (Object.keys(nombres) as NivelHallazgo[])
    .filter((n) => (conteo[n] ?? 0) > 0)
    .map((n) => `${conteo[n]} ${nombres[n][(conteo[n] ?? 0) === 1 ? 0 : 1]}`);
  return partes.join(" · ") || "Sin hallazgos";
}

/** Estado del registro para el encabezado: oficial o borrador y la versión que se emitirá. */
export function estadoRegistro(r: ResumenPrivacidad["registro"]): { texto: string; tono: string } {
  return r.oficial
    ? { texto: `Registro oficial · versión ${r.version_siguiente}`, tono: "tone-ok" }
    : { texto: `Borrador · versión ${r.version_siguiente}`, tono: "tone-medio" };
}

/** Cuántos plazos salen de un ajuste configurado (con número) y cuántos dependen de una decisión pendiente. */
export function contarPlazos(actividades: Actividad[]): { automaticos: number; total: number } {
  const plazos = actividades.flatMap((a) => a.plazos);
  return { automaticos: plazos.filter((p) => p.dias != null).length, total: plazos.length };
}

/** Columna del mapa donde va cada elemento: quien opera, dónde se guarda y a quién se envía. */
export function columnaMapa(e: ElementoMapa): "operacion" | "almacenamiento" | "proveedores" {
  if (e.tipo === "tercero") return "proveedores";
  return e.tipo === "sistema" ? "operacion" : "almacenamiento";
}

/** Mensaje del formulario del RoPA para un campo (lo que falta o lo que rechazó el servidor). */
export function mensajeCampoRopa(faltantes: FaltanteRopa[], campo: keyof DatosRopa, rechazo?: { campo?: string; mensaje: string } | null): string | null {
  if (rechazo?.campo === campo) return rechazo.mensaje;
  return faltantes.find((f) => f.campo === campo)?.mensaje ?? null;
}

/** Solo los campos que cambiaron (null borra el valor), para no reescribir lo demás. */
export function cambiosRopa(antes: DatosRopa, despues: DatosRopa): Partial<DatosRopa> {
  const salida: Partial<DatosRopa> = {};
  (Object.keys(despues) as (keyof DatosRopa)[]).forEach((k) => {
    const nuevo = typeof despues[k] === "string" ? ((despues[k] as string).trim() || null) : despues[k];
    if (nuevo !== antes[k]) (salida as Record<string, unknown>)[k] = nuevo;
  });
  return salida;
}

/** El código verificable tiene forma CIA-PLAT-REG-AAAA-NNNNNN-D o CIA-PLAT-ROPA-…: se revisa antes de enviar. */
export function codigoBienFormado(codigo: string): boolean {
  return /^CIA-PLAT-(REG|ROPA)-\d{4}-\d{6,9}-[0-9K]$/i.test(codigo.trim());
}
