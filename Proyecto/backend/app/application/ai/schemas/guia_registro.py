"""
Salida estructurada de la guía de registro: una respuesta corta y, opcionalmente, dos preguntas que la
persona podría hacer después. No hay propuestas: la guía no arma ni rellena registros.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GuiaRegistroRespuesta(BaseModel):
    fuera_de_alcance: bool
    respuesta: str = Field(description="Entre una y cuatro frases simples.")
    sugerencias: list[str] = Field(description="Hasta 2 preguntas cortas para seguir.")
