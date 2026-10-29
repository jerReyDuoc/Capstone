/**
 * Correcciones 29-10 · Textos del cuestionario que ve el encuestado o el cliente.
 *
 * Al usuario le hablamos de "preguntas", nunca de "controles", y no le mostramos los códigos
 * internos del catálogo (DAT-001, GOB-003…) ni cuántos controles activa cada respuesta: eso
 * expone la metodología y la documentación interna de Therion Labs.
 *
 * Las descripciones de las preguntas iniciales vienen de la semilla del backend y explican la
 * metodología ("Activa controles de…"); aquí se reemplazan por una ayuda pensada para quien
 * responde, sin tocar la base de datos.
 */
export const AYUDA_FILTRO: Record<string, string> = {
  F1: "Considera cualquier uso: desde herramientas como ChatGPT o Copilot hasta modelos propios.",
  F2: "Por ejemplo, fichas de salud, huellas o rostros, o perfiles de comportamiento de clientes o de menores de edad.",
  F3: "Por ejemplo, APIs o plataformas de IA de otras empresas, o servicios en la nube alojados fuera de Chile.",
  F4: "Asistentes conversacionales, generación de textos o imágenes, o búsquedas con IA sobre documentos internos.",
  F5: "Por ejemplo, asistentes que escriben código o consultas, o agentes que envían correos o modifican registros.",
  F6: "Por ejemplo, evaluación de crédito, selección de personal o priorización de atención a personas.",
  F7: "Incluye entrenar o ajustar modelos con datos de la empresa.",
};

/** Ayuda de una pregunta inicial: la propia si existe; la del backend solo si no habla de controles. */
export function ayudaFiltro(codigo: string, descripcionBackend: string | null | undefined): string | null {
  if (AYUDA_FILTRO[codigo]) return AYUDA_FILTRO[codigo];
  if (!descripcionBackend || /control/i.test(descripcionBackend)) return null;
  return descripcionBackend;
}

/** "1 pregunta" / "3 preguntas". */
export const preguntas = (n: number) => `${n} ${n === 1 ? "pregunta" : "preguntas"}`;
