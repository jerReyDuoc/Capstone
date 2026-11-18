/**
 * Correcciones 05-11 · Fechas y horas en hora de Chile (America/Santiago).
 *
 * El backend guarda y devuelve las fechas en UTC SIN zona ("2026-11-05T18:21:00"). El navegador
 * interpreta ese formato como hora LOCAL, así que el panel admin mostraba la hora UTC (3 horas
 * más) o la del equipo de quien miraba. Aquí:
 *   - una fecha sola ("2026-11-05") se toma como ese día (al mediodía, para que ningún huso la
 *     cambie de día);
 *   - una fecha-hora sin zona se toma como UTC (se le agrega "Z");
 *   - todo se muestra con la zona horaria de Chile, con horario de verano incluido.
 */
export const ZONA_CHILE = "America/Santiago";

export function fechaDelServidor(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const t = iso.trim();
  let d: Date;
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) d = new Date(`${t}T12:00:00Z`);
  else if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(t)) d = new Date(t);
  else d = new Date(`${t.replace(" ", "T")}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

const F_FECHA = new Intl.DateTimeFormat("es-CL", { timeZone: ZONA_CHILE, day: "numeric", month: "short", year: "numeric" });
const F_FECHA_NUM = new Intl.DateTimeFormat("es-CL", { timeZone: ZONA_CHILE, day: "2-digit", month: "2-digit", year: "numeric" });
const F_HORA = new Intl.DateTimeFormat("es-CL", { timeZone: ZONA_CHILE, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const F_HORA_SEG = new Intl.DateTimeFormat("es-CL", {
  timeZone: ZONA_CHILE, hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
});

/** "5 nov 2026" */
export function fechaChile(iso: string | null | undefined): string {
  const d = fechaDelServidor(iso);
  return d ? F_FECHA.format(d).replace(/\./g, "") : "—";
}

/** "05-11-2026" */
export function fechaNumericaChile(iso: string | null | undefined): string {
  const d = fechaDelServidor(iso);
  return d ? F_FECHA_NUM.format(d) : "—";
}

/** "5 nov 2026, 15:21" (o con segundos, para la bitácora). */
export function fechaHoraChile(iso: string | null | undefined, conSegundos = false): string {
  const d = fechaDelServidor(iso);
  if (!d) return "—";
  return `${F_FECHA.format(d).replace(/\./g, "")}, ${(conSegundos ? F_HORA_SEG : F_HORA).format(d)}`;
}

/** "15:21" de un Date del navegador (p. ej. la hora de la última actualización). */
export const horaChile = (d: Date) => F_HORA.format(d);

/**
 * Auditoría UX 16-11 · "Actualizado hace X": tiempo relativo corto, en español de Chile.
 * Se usa en vez de un botón "Actualizar" por página (los datos se recargan solos al volver).
 */
export function haceTexto(desde: Date, ahora: Date = new Date()): string {
  const s = Math.max(0, Math.round((ahora.getTime() - desde.getTime()) / 1000));
  if (s < 45) return "hace un momento";
  const min = Math.round(s / 60);
  if (min < 60) return min === 1 ? "hace 1 minuto" : `hace ${min} minutos`;
  const h = Math.round(min / 60);
  if (h < 24) return h === 1 ? "hace 1 hora" : `hace ${h} horas`;
  const d = Math.round(h / 24);
  return d === 1 ? "hace 1 día" : `hace ${d} días`;
}

const F_HORA_UTC = new Intl.DateTimeFormat("es-CL", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" });
const F_DIA_CHILE = new Intl.DateTimeFormat("en-CA", { timeZone: ZONA_CHILE });

/**
 * Auditoría UX 16-11 · Hora con sus dos zonas para que no parezca contradictoria:
 * "hoy 00:00 (Chile) · 03:00 UTC". `hoy`/`mañana` según el calendario de Chile.
 */
export function horaConZonas(instante: Date, ahora: Date = new Date()): string {
  const dia = F_DIA_CHILE.format(instante);
  const hoy = F_DIA_CHILE.format(ahora);
  const manana = F_DIA_CHILE.format(new Date(ahora.getTime() + 86_400_000));
  const prefijo = dia === hoy ? "hoy" : dia === manana ? "mañana" : fechaChile(instante.toISOString());
  return `${prefijo} ${horaChile(instante)} (Chile) · ${F_HORA_UTC.format(instante)} UTC`;
}
