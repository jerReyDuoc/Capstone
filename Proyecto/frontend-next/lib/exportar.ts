/**
 * HU-11 · Exportación del listado de brechas.
 *
 * - CSV: para llevar el listado a un dashboard externo (Power BI, Looker Studio, Excel).
 *   Separador ";" y BOM UTF-8 para que Excel en es-CL lo abra con tildes y columnas bien.
 * - PDF: se genera con el diálogo de impresión del navegador ("Guardar como PDF") sobre una
 *   versión del informe diseñada para papel (ver @media print en globals.css). Así el PDF
 *   lleva texto real y seleccionable, sin agregar dependencias al proyecto.
 */
import type { BrechaVista, EstadoBrecha } from "./types";

export const ETIQUETA_ESTADO_LARGA: Record<EstadoBrecha, string> = {
  no_cumplido: "No cumplido",
  parcialmente_cumplido: "Parcialmente cumplido",
};

const COLUMNAS: [string, (b: BrechaVista) => string | number | null][] = [
  ["Prioridad", (b) => b.prioridad],
  ["Severidad", (b) => b.severidad],
  ["Código brecha", (b) => b.codigo],
  ["Código control", (b) => b.controlCodigo],
  ["Dominio", (b) => b.dominio],
  ["Estado", (b) => ETIQUETA_ESTADO_LARGA[b.estado]],
  ["Impacto del control", (b) => b.criticidad],
  ["Brecha detectada", (b) => b.descripcion],
  ["Acción sugerida", (b) => b.accion],
  ["Ruta formativa", (b) => b.rutaFormativa],
];

/**
 * Celda CSV segura:
 * - comillas dobles escapadas y todo entre comillas;
 * - si empieza con = + - @ (o tab/CR) se antepone ' para que Excel no la ejecute como
 *   fórmula (inyección CSV / OWASP).
 */
export function celdaCsv(valor: string | number | null | undefined): string {
  if (valor == null) return '""';
  let s = String(valor);
  if (typeof valor === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return `"${s.replace(/"/g, '""')}"`;
}

export function brechasACsv(brechas: BrechaVista[], separador = ";"): string {
  const filas = [
    COLUMNAS.map(([titulo]) => celdaCsv(titulo)).join(separador),
    ...brechas.map((b) => COLUMNAS.map(([, valor]) => celdaCsv(valor(b))).join(separador)),
  ];
  return `﻿${filas.join("\r\n")}\r\n`;
}

/** brechas_evaluacion-9101_2026-10-21 (sin extensión: el PDF lo usa como título del documento). */
export function nombreArchivo(evaluacionId: number, fecha: Date = new Date()): string {
  const yyyy = fecha.getFullYear();
  const mm = String(fecha.getMonth() + 1).padStart(2, "0");
  const dd = String(fecha.getDate()).padStart(2, "0");
  return `brechas_evaluacion-${evaluacionId}_${yyyy}-${mm}-${dd}`;
}

/** Descarga un texto como archivo (solo navegador). */
export function descargarTexto(contenido: string, nombre: string, tipo = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([contenido], { type: tipo }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Se libera después del clic para que Safari alcance a iniciar la descarga.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Abre el diálogo de impresión con el título del documento = nombre del archivo,
 * que es el nombre que proponen Chrome, Edge y Firefox al "Guardar como PDF".
 */
export function imprimirComoPdf(nombre: string) {
  const anterior = document.title;
  const restaurar = () => {
    document.title = anterior;
    window.removeEventListener("afterprint", restaurar);
  };
  document.title = nombre;
  window.addEventListener("afterprint", restaurar);
  window.print();
}
