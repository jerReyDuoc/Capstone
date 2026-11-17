from __future__ import annotations

from pydantic import BaseModel, Field


class VistaRequest(BaseModel):
    evaluacion_id: int | None = Field(None, ge=1)


class VerificacionRequest(BaseModel):
    # {pregunta_id: id de la opción elegida}
    respuestas: dict[int, int] = Field(default_factory=dict, max_length=50)
    evaluacion_id: int | None = Field(None, ge=1)
