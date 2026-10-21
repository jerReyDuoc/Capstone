/**
 * HU-19 · Datos de la petición entrante (compatible con Edge: la usa middleware.ts).
 */

/**
 * IP del visitante para los límites por IP.
 *
 * TRUSTED_PROXY_HOPS = cuántos proxies de confianza hay DELANTE del servidor de Next
 * (0 en local/docker compose, 1 detrás de un nginx o un balanceador, etc.). Se toma la
 * entrada de X-Forwarded-For que agregó el proxy más externo de confianza: las de la
 * izquierda las puede inventar el cliente y no se usan.
 */
export function ipCliente(headers: Headers, saltos = Number(process.env.TRUSTED_PROXY_HOPS ?? 0)): string {
  const hops = Number.isInteger(saltos) && saltos >= 0 ? saltos : 0;
  const cadena = (headers.get("x-forwarded-for") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const candidata = cadena.length ? cadena[Math.max(0, cadena.length - 1 - hops)] : headers.get("x-real-ip") ?? "";
  return /^[0-9a-fA-F:.]{2,45}$/.test(candidata) ? candidata : "desconocida";
}

/**
 * Defensa CSRF para todo lo que no sea GET: la petición debe venir de este mismo sitio.
 * Los navegadores actuales envían Sec-Fetch-Site; los anteriores, Origin.
 */
export function esMismoOrigen(headers: Headers): boolean {
  const sitio = headers.get("sec-fetch-site");
  if (sitio) return sitio === "same-origin";
  const origen = headers.get("origin");
  const host = headers.get("x-forwarded-host") ?? headers.get("host");
  if (!origen || !host) return false;
  try {
    return new URL(origen).host === host.split(",")[0].trim();
  } catch {
    return false;
  }
}
