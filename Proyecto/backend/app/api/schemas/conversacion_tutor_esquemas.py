from __future__ import annotations

from pydantic import BaseModel, Field


class NuevaConversacion(BaseModel):
    ruta_id: int | None = Field(None, ge=1, description="Módulo formativo desde el que se abre (fija el nivel por defecto)")
    nivel: str | None = Field(None, max_length=20, description="Inicial | Intermedio | Avanzado (vacío = el de la ruta)")


class CambioNivel(BaseModel):
    nivel: str = Field(..., max_length=20)


class NuevoMensaje(BaseModel):
    # El largo real lo controla TUTOR_MAX_CHARS_MENSAJE en el caso de uso; esto es un tope duro.
    texto: str = Field(..., max_length=20000)
