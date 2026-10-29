"""
Adaptador: implementa EvidenceValidatorPort usando el agente de IA.

ProcessEvidenceUseCase sigue dependiendo del mismo puerto de siempre. Desde HU-15 la
validación de evidencias es una SKILL del agente de LangGraph (app/application/ai/agente):
el agente la enruta a su nodo y ese nodo llama al AIGateway con la tarea
VALIDAR_EVIDENCIA, así que sanitización, prompt, proveedor y métricas no cambian.
"""
from app.application.ai.agente import AgenteIA, SkillIA
from app.application.ai.gateway import AIGateway
from app.application.schemas.evidence_validation import EvidenceValidation
from app.domain.ports.evidence_validator_port import EvidenceValidatorPort
from app.domain.ports.registro_ia_port import ContextoLlamada


class GatewayEvidenceValidator(EvidenceValidatorPort):
    def __init__(self, gateway: AIGateway, agente: AgenteIA | None = None):
        self.gateway = gateway
        self.agente = agente or AgenteIA(gateway)

    async def validate(
        self,
        contenido,
        control,
        respuesta,
        brecha=None,
        justificacion=None,
        contexto: ContextoLlamada | None = None,
    ) -> EvidenceValidation:
        if justificacion is None:
            justificacion = respuesta.justificacion_usuario
        salida = await self.agente.ejecutar(
            SkillIA.VALIDAR_EVIDENCIA,
            textos={"evidencia": contenido, "justificacion": justificacion},
            datos={"control": control, "respuesta": respuesta, "brecha": brecha},
            contexto=contexto,
        )
        return salida.resultado.data
