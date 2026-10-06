from langchain_groq import ChatGroq
from app.core.config import settings
from app.domain.ports.evidence_validator_port import EvidenceValidatorPort
from app.application.schemas.evidence_validation import EvidenceValidation
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.catalogo_brechas import CatalogoBrechas


class GroqEvidenceValidator(EvidenceValidatorPort):
    def __init__(self):
        self.llm = ChatGroq(
            model=settings.LLM_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0,
        ).with_structured_output(EvidenceValidation)

    async def validate(
        self,
        contenido: str,
        control: MatrizControl,
        respuesta: Respuesta,
        brecha: CatalogoBrechas | None = None,
    ) -> EvidenceValidation:
        prompt = self._build_prompt(contenido, control, respuesta, brecha)
        return await self.llm.ainvoke(prompt)

    def _build_prompt(
        self,
        contenido: str,
        control: MatrizControl,
        respuesta: Respuesta,
        brecha: CatalogoBrechas | None,
    ) -> str:
        brecha_contexto = ""
        if brecha:
            brecha_contexto = f"""
BRECHA ASOCIADA A ESTE CONTROL (referencia para tu evaluación):
- Categoría: {brecha.categoria}
- Comportamiento que indica incumplimiento: {brecha.comportamiento_detectado}
- Criticidad: {brecha.criticidad}
"""

        return f"""Eres un auditor experto en gobernanza, riesgo y cumplimiento de IA,
con conocimiento profundo de la Ley chilena N.º 21.719, ISO/IEC 42001 y NIST AI RMF 100-1.

Tu tarea es evaluar si la evidencia adjunta respalda la clasificación que el usuario
declaró para un control específico. Debes ser riguroso: si la evidencia no alcanza
el estándar, debes degradar la clasificación.

═══════════════════════════════════════════════════════════════
CONTEXTO NORMATIVO DEL CONTROL
═══════════════════════════════════════════════════════════════
- Código: {control.codigo_control or "N/A"}
- Framework: {control.framework_fuente or "N/A"}
- Artículo/Cláusula: {control.articulo_referencia or "N/A"}
- Tipo de fuente: {control.tipo_fuente or "N/A"}
- Criticidad del control: {control.criticidad or "N/A"}
- Aplicabilidad: {control.aplicabilidad or "N/A"}

═══════════════════════════════════════════════════════════════
CONTROL A EVALUAR
═══════════════════════════════════════════════════════════════
- Obligación: {control.obligacion or "N/A"}
- Pregunta: {control.pregunta_evaluacion or "N/A"}

═══════════════════════════════════════════════════════════════
EVIDENCIA ESPERADA SEGÚN EL FRAMEWORK
═══════════════════════════════════════════════════════════════
{control.evidencia_esperada or "No especificada en el framework."}

{brecha_contexto}

═══════════════════════════════════════════════════════════════
RESPUESTA DEL USUARIO
═══════════════════════════════════════════════════════════════
- Clasificación declarada: {respuesta.estado_clasificacion or "N/A"}
- Justificación del usuario: {respuesta.justificacion_usuario or "Sin justificación"}

═══════════════════════════════════════════════════════════════
EVIDENCIA ADJUNTA (extracto)
═══════════════════════════════════════════════════════════════
{contenido[:8000]}

═══════════════════════════════════════════════════════════════
REGLAS DE CLASIFICACIÓN
═══════════════════════════════════════════════════════════════
- "cumplido": la evidencia demuestra el cumplimiento completo del control,
  coincide con la evidencia esperada del framework.
- "parcialmente_cumplido": la evidencia demuestra cumplimiento parcial,
  hay avances documentados pero faltan elementos exigidos por el framework.
- "no_cumplido": la evidencia NO respalda el cumplimiento, o contradice
  lo declarado por el usuario, o es insuficiente para demostrar cumplimiento.

REGLAS ADICIONALES:
1. Si el usuario declaró "cumplido" o "parcialmente_cumplido" pero la evidencia
   no alcanza ese nivel, DEBES degradar la clasificación.
2. Si el usuario declaró "cumplido" pero la evidencia solo sustenta cumplimiento
   parcial, DEBES devolver "parcialmente_cumplido".
3. Sé estricto con la evidencia esperada: si el framework exige un informe
   firmado y la evidencia es solo una captura de pantalla, degrada.
4. Marca "evidencia_suficiente=false" solo si el archivo no contiene información
   útil para evaluar (ej. está vacío, es ilegible, o es un archivo irrelevante).
5. Tu justificación debe citar elementos concretos de la evidencia y del framework.

Devuelve tu evaluación en el formato estructurado solicitado.
"""