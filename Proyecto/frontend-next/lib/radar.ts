/**
 * Geometría del gráfico de radar del Diagnóstico (lógica pura, probada en tests/mejoras_1911.test.ts).
 *
 * Cada dimensión es un eje que sale del centro; el primero apunta hacia arriba y los demás siguen
 * en sentido horario. Con 4 dimensiones (las del modelo de madurez) la figura es un rombo.
 * Los valores van de 0 a 100: 0 es el centro y 100 el borde.
 */

export interface PuntoRadar {
  x: number;
  y: number;
}

export const limitar = (v: number | null | undefined) => Math.max(0, Math.min(100, Number.isFinite(v) ? (v as number) : 0));

const redondear = (n: number) => Math.round(n * 100) / 100;

/** Ángulo (radianes) del eje i de n: el primero hacia arriba, sentido horario. */
export function anguloEje(i: number, n: number): number {
  return -Math.PI / 2 + (2 * Math.PI * i) / n;
}

/** Posición del valor (0-100) sobre el eje i. */
export function puntoEnEje(cx: number, cy: number, radio: number, valor: number, i: number, n: number): PuntoRadar {
  const r = (limitar(valor) / 100) * radio;
  const a = anguloEje(i, n);
  return { x: redondear(cx + r * Math.cos(a)), y: redondear(cy + r * Math.sin(a)) };
}

/** Atributo `points` de un <polygon> con un valor por eje. */
export function poligonoRadar(valores: number[], cx: number, cy: number, radio: number): string {
  return valores
    .map((v, i) => puntoEnEje(cx, cy, radio, v, i, valores.length))
    .map((p) => `${p.x},${p.y}`)
    .join(" ");
}

/** Alineación de la etiqueta del eje según hacia dónde apunta (izquierda, centro o derecha). */
export function anclaEtiqueta(i: number, n: number): "start" | "middle" | "end" {
  const c = Math.cos(anguloEje(i, n));
  if (c > 0.3) return "start";
  if (c < -0.3) return "end";
  return "middle";
}

/**
 * Parte el nombre de una dimensión en líneas de hasta `max` caracteres (sin cortar palabras),
 * para que las etiquetas no se salgan del gráfico. Máximo 3 líneas.
 */
export function partirEtiqueta(texto: string, max = 14): string[] {
  const lineas: string[] = [];
  for (const palabra of texto.trim().split(/\s+/)) {
    const ultima = lineas[lineas.length - 1];
    if (ultima !== undefined && `${ultima} ${palabra}`.length <= max) lineas[lineas.length - 1] = `${ultima} ${palabra}`;
    else lineas.push(palabra);
  }
  // Sin palabras cortas huérfanas: "Gobernanza de IA" → "Gobernanza" / "de IA" (no "Gobernanza de" / "IA")
  const n = lineas.length;
  if (n > 1 && lineas[n - 1].length <= 3 && lineas[n - 2].includes(" ")) {
    const previa = lineas[n - 2];
    const corte = previa.lastIndexOf(" ");
    lineas[n - 2] = previa.slice(0, corte);
    lineas[n - 1] = `${previa.slice(corte + 1)} ${lineas[n - 1]}`;
  }
  if (lineas.length <= 3) return lineas;
  return [...lineas.slice(0, 2), lineas.slice(2).join(" ")];
}
