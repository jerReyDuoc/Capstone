from typing import Literal
from pydantic import BaseModel, Field

class EvidenceValidation(BaseModel):
    """
    Resultado de la validación del LLM sobre una evidencia.

    El LLM SOLO evalúa si la evidencia respalda lo declarado por el usuario
    y propone una clasificación. NO asigna brechas, NO toca la BD,
    NO tiene acceso a información fuera del prompt.
    """
    clasificacion: Literal["cumplido", "parcialmente_cumplido", "no_cumplido"] = Field(
        description="Clasificación que el LLM considera correcta según la evidencia"
    )
    confianza: float = Field(ge=0, le=1, description="Confianza de 0 a 1")
    justificacion: str = Field(
        description="Explicación detallada de por qué el LLM propone esa clasificación"
    )
    respalda_clasificacion_usuario: bool = Field(
        description="True si coincide con lo declarado por el usuario"
    )
    divergencia_explicada: str | None = Field(
        default=None,
        description="Si NO respalda al usuario, explicar la divergencia (obligatorio en ese caso)"
    )
    evidencia_suficiente: bool = Field(
        description="True si la evidencia es suficiente para sustentar CUALQUIER clasificación"
    )
    datos_extraidos: dict = Field(default_factory=dict)
    errores: list[str] = Field(default_factory=list)