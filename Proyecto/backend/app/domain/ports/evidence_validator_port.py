from abc import ABC, abstractmethod
from app.application.schemas.evidence_validation import EvidenceValidation
from app.domain.models.matriz_control import MatrizControl
from app.domain.models.respuesta import Respuesta
from app.domain.models.catalogo_brechas import CatalogoBrechas


class EvidenceValidatorPort(ABC):
    @abstractmethod
    async def validate(
        self,
        contenido: str,
        control: MatrizControl,
        respuesta: Respuesta,
        brecha: CatalogoBrechas | None = None,
    ) -> EvidenceValidation:
        """
        Valida una evidencia contra el control y la clasificación declarada.
        El LLM NO tiene acceso a la BD: solo recibe este prompt y devuelve JSON.
        """
        ...