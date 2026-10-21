/**
 * HU-04 · Aviso legal de la encuesta pública.
 *
 * BORRADOR TÉCNICO: el texto lo debe aprobar el Product Owner (y asesoría legal si
 * corresponde) antes del piloto. Al cambiar el texto, sube AVISO_LEGAL_VERSION aquí
 * y en el backend (variable AVISO_LEGAL_VERSION): una versión distinta obliga a
 * aceptar de nuevo (409 AVISO_DESACTUALIZADO).
 */
export const AVISO_LEGAL_VERSION = "2026-10-v1";

export interface SeccionAviso {
  titulo: string;
  texto: string;
}

export const AVISO_LEGAL: SeccionAviso[] = [
  {
    titulo: "Quién trata los datos",
    texto:
      "ComplianceAI es un servicio de TherionLabs para autodiagnosticar la madurez de una organización en " +
      "gobernanza de inteligencia artificial y cumplimiento de la Ley N.º 21.719 de protección de datos personales.",
  },
  {
    titulo: "Para qué",
    texto:
      "Usamos tus respuestas para calcular el nivel de madurez de tu organización, mostrarte brechas y rutas " +
      "formativas y, si la evaluación queda completa, compararla de forma agregada y anónima con otras del mismo rubro.",
  },
  {
    titulo: "Qué datos y cómo se protegen",
    texto:
      "No pedimos tu nombre ni el de tu organización. El correo es opcional. Antes de guardar o enviar al modelo de " +
      "IA, el texto de las justificaciones y evidencias se anonimiza (se reemplazan RUT, nombres, correos, teléfonos " +
      "y direcciones). Te recomendamos no subir documentos con datos personales que no sean necesarios.",
  },
  {
    titulo: "Uso de inteligencia artificial",
    texto:
      "Un modelo de IA sugiere la clasificación de algunas respuestas a partir de las evidencias. Sus sugerencias " +
      "son orientativas y pueden ser revisadas por una persona.",
  },
  {
    titulo: "Tus derechos",
    texto:
      "Puedes ejercer tus derechos de acceso, rectificación, supresión, oposición, portabilidad y bloqueo con tu " +
      "número de evaluación y tu clave. Conservamos la evaluación incompleta por un tiempo limitado.",
  },
];
