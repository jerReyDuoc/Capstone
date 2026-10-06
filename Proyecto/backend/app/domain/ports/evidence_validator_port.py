from abc import ABC, abstractmethod
from app.application.schemas.evidence_validation import EvidenceValidation
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta

class EvidenceValidatorPort(ABC):
    @abstractmethod
    async def validate(
        self,
        contenido: str,
        control: MatrizControl,
        respuesta: Respuesta,
    ) -> EvidenceValidation: ...