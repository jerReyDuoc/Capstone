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
