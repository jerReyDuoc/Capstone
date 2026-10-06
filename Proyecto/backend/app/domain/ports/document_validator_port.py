from abc import ABC, abstractmethod
from app.application.schemas.validation import ValidationResult

class DocumentValidatorPort(ABC):
    @abstractmethod
    async def validate(self, content: str, filename: str) -> ValidationResult:
        """Valida el contenido de un documento y devuelve el resultado estructurado."""
        ...
