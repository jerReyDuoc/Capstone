/**
 * Auditoría UX 16-11 · Fase 6.3: diccionario único de siglas. La primera vez que una sigla aparece
 * en una pantalla se muestra el nombre completo; las siguientes usan <Sigla> (nombre completo
 * accesible con el foco y el mouse, y para lectores de pantalla).
 */
export const SIGLAS = {
  RoPA: "registro de las actividades de tratamiento",
  RAT: "registro de actividades de tratamiento",
  PIA: "evaluación de impacto en la protección de datos",
  ARCOP: "derechos de acceso, rectificación, cancelación, oposición y portabilidad",
  DPO: "delegado de protección de datos",
  NNA: "niños, niñas y adolescentes",
} as const;

export type CodigoSigla = keyof typeof SIGLAS;

/** "Evaluación de impacto en la protección de datos (PIA)". */
export const conNombreCompleto = (s: CodigoSigla) => {
  const n = SIGLAS[s];
  return `${n.charAt(0).toUpperCase()}${n.slice(1)} (${s})`;
};
