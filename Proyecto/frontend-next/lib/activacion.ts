/**
 * HU-27 · Lógica pura del enlace de activación (navegador y BFF; probada en tests/).
 *
 * El correo trae  https://…/activar#token=XXXX : el token va en el FRAGMENTO, que el
 * navegador nunca envía al servidor (no queda en logs de acceso ni en el Referer).
 */

const FORMATO_TOKEN = /^[A-Za-z0-9_-]{20,128}$/;

export function tokenActivacionValido(t: unknown): t is string {
  return typeof t === "string" && FORMATO_TOKEN.test(t);
}

/** "#token=abc" → "abc" (o null si falta o no tiene el formato esperado). */
export function tokenDesdeFragmento(hash: string): string | null {
  const limpio = hash.startsWith("#") ? hash.slice(1) : hash;
  const valor = new URLSearchParams(limpio).get("token");
  return tokenActivacionValido(valor) ? valor : null;
}

/**
 * Las mismas reglas que valida el backend (activacion_cuenta.validar_contrasena), para avisar
 * antes de enviar. El backend es la única autoridad: aquí solo se anticipa.
 */
export function problemasContrasena(pw: string, minimo = 12): string[] {
  const p: string[] = [];
  if (pw.length < minimo) p.push(`Debe tener al menos ${minimo} caracteres.`);
  if (pw.length > 128) p.push("Debe tener como máximo 128 caracteres.");
  if (!/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(pw) || !/\d/.test(pw)) p.push("Debe combinar letras y números.");
  if (pw && pw.trim() !== pw) p.push("No puede empezar ni terminar con espacios.");
  return p;
}
