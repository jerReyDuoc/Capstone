"""
Adaptador: implementa EvidenceValidatorPort usando el AIGateway.

ProcessEvidenceUseCase sigue dependiendo del mismo puerto de siempre; la diferencia
es que ahora la sanitización, el prompt, el proveedor y las métricas viven en la
capa de IA y no en el caso de uso ni en un adaptador atado a Groq.
"""
from app.application.ai.gateway import AIGateway
from app.application.ai.politicas import TareaIA
from app.application.schemas.evidence_validation import EvidenceValidation
from app.domain.ports.evidence_validator_port import EvidenceValidatorPort
from app.domain.ports.registro_ia_port import ContextoLlamada


class GatewayEvidenceValidator(EvidenceValidatorPort):
    def __init__(self, gateway: AIGateway):
        self.gateway = gateway

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
        resultado = await self.gateway.ejecutar(
            TareaIA.VALIDAR_EVIDENCIA,
            textos={"evidencia": contenido, "justificacion": justificacion},
            datos={"control": control, "respuesta": respuesta, "brecha": brecha},
            contexto=contexto,
        )
        return resultado.data
