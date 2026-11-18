/**
 * Auditoría UX 16-11 · Fase 8.B: UN flujo para armar el registro de actividades.
 *
 *   1) Mapa de datos  →  2) Completar con el asistente  →  3) Revisar el registro
 *
 * Las tres pantallas existentes son los pasos (sus URL no cambian). La entrada única
 * (/empresa/registro) lleva directo al paso pendiente. Lógica pura (tests/flujo_registro.test.ts).
 */
export type NumeroPaso = 1 | 2 | 3;

export interface PasoRegistro {
  numero: NumeroPaso;
  titulo: string;
  descripcion: string;
  href: string;
  /** El asistente se abre con ?asistente=1 al cargar: necesita una navegación completa. */
  recargaCompleta?: boolean;
}

export const PASOS_REGISTRO: PasoRegistro[] = [
  { numero: 1, titulo: "Mapa de datos", descripcion: "Qué datos tratas, dónde están y con quién los compartes.", href: "/empresa/mapa-datos" },
  {
    numero: 2,
    titulo: "Completar con el asistente",
    descripcion: "Conversa con el asistente para proponer tus actividades a partir del mapa.",
    href: "/empresa/mapa-datos?asistente=1",
    recargaCompleta: true,
  },
  { numero: 3, titulo: "Revisar el registro", descripcion: "Revisa cada actividad, complétala y déjala vigente.", href: "/empresa/registro-actividades" },
];

export interface AvanceRegistro {
  mapaIniciado: boolean;
  elementos: number;
  actividades: number;
}

/** El paso que falta hacer. */
export function pasoPendiente(a: AvanceRegistro): NumeroPaso {
  if (!a.mapaIniciado || a.elementos === 0) return 1;
  if (a.actividades === 0) return 2;
  return 3;
}

/** En qué paso está la persona según la página que mira. */
export function pasoDeRuta(pathname: string, asistenteAbierto: boolean): NumeroPaso | null {
  if (pathname.startsWith("/empresa/registro-actividades")) return 3;
  if (pathname.startsWith("/empresa/mapa-datos") || pathname.startsWith("/empresa/asistente")) return asistenteAbierto ? 2 : 1;
  return null;
}

export type EstadoPaso = "hecho" | "actual" | "pendiente";

export function estadoPasos(actual: NumeroPaso, pendiente: NumeroPaso): Record<NumeroPaso, EstadoPaso> {
  const de = (n: NumeroPaso): EstadoPaso => (n === actual ? "actual" : n < pendiente ? "hecho" : "pendiente");
  return { 1: de(1), 2: de(2), 3: de(3) };
}
