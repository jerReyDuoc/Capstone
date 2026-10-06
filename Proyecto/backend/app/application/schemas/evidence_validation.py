from typing import Literal
from pydantic import BaseModel, Field

class EvidenceValidation(BaseModel):
    clasificacion: Literal["verde", "amarillo", "rojo"] = Field(
        description="Clasificación final propuesta por el LLM"
    )
    confianza: float = Field(ge=0, le=1, description="Confianza de 0 a 1")
    justificacion: str = Field(description="Explicación de la clasificación")
    respalda_clasificacion_usuario: bool = Field(
        description="True si coincide con lo declarado por el usuario"
    )
    divergencia_explicada: str | None = Field(
        default=None,
        description="Si no respalda al usuario, explicar por qué"
    )
    datos_extraidos: dict = Field(default_factory=dict)
    errores: list[str] = Field(default_factory=list)