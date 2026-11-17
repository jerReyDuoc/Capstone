from __future__ import annotations

from pydantic import BaseModel, Field


class NuevoBorrador(BaseModel):
    tipo: str = Field(..., max_length=30, description="politica_llm | aviso_privacidad | pia")
    # El largo real lo controla BORRADORES_MAX_CHARS_INSTRUCCIONES en el caso de uso; esto es un tope duro.
    instrucciones: str | None = Field(None, max_length=20000,
                                      description="Preferencias de redacción para el Agente IA (opcional)")
    usar_ia: bool = Field(True, description="false = solo la plantilla y la evaluación, sin llamar al LLM")
    evaluacion_id: int | None = Field(None, ge=1, description="Vacío = la evaluación más reciente de la empresa")
    # HU-38: actividades del registro que evalúa la PIA (vacío = las que tienen la evaluación recomendada)
    actividades: list[int] | None = Field(None, max_length=10,
                                          description="Ids de actividades del registro para la PIA (opcional)")


class EdicionBorrador(BaseModel):
    # Tope duro; el real es BORRADORES_MAX_CHARS_CONTENIDO
    contenido: str = Field(..., max_length=100000)
    version: int = Field(..., ge=1, description="La versión que se editó (control de edición concurrente)")


class Consolidacion(BaseModel):
    version: int = Field(..., ge=1)
    confirmar_pendientes: bool = Field(False, description="Consolidar aunque queden campos [COMPLETAR: ...]")
