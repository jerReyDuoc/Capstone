from langchain_groq import ChatGroq
from app.core.config import settings
from app.domain.ports.evidence_validator_port import EvidenceValidatorPort
from app.application.schemas.evidence_validation import EvidenceValidation
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta

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
    ) -> EvidenceValidation:
        prompt = f"""Eres un auditor experto en modelos de madurez organizacional.
Debes validar la evidencia que un usuario adjuntó para respaldar su respuesta
a un control de evaluación.

CONTROL A EVALUAR:
- Pregunta: {control.pregunta_evaluacion or "No especificada"}
- Obligación: {control.obligacion or "No especificada"}

RESPUESTA DEL USUARIO:
- Clasificación declarada: {respuesta.estado_clasificacion or "No especificada"}
- Justificación: {respuesta.justificacion_usuario or "Sin justificación"}

EVIDENCIA ADJUNTA:
---
{contenido[:8000]}
---

Reglas de clasificación:
- VERDE: la evidencia respalda completamente la clasificación declarada.
- AMARILLO: la evidencia respalda parcialmente o con observaciones menores.
- ROJO: la evidencia no respalda o contradice la clasificación declarada.

Devuelve tu clasificación con nivel de confianza (0-1), justificación clara,
y si respaldas o no la clasificación del usuario. Si no la respaldas, explica
la divergencia de forma obligatoria.
"""
        return await self.llm.ainvoke(prompt)