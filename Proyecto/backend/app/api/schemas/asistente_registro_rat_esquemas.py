from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NuevaSesion(BaseModel):
    area: str | None = Field(default=None, max_length=20)


class CambioArea(BaseModel):
    area: str = Field(max_length=20)


class Respuesta(BaseModel):
    texto: str | None = Field(default=None, max_length=8000)
    omitir: bool = False
    sin_ia: bool = False   # guardar sin ayuda automática (cuando la ayuda falló)


class Aceptacion(BaseModel):
    payload: dict | None = None
    version_mapa: int | None = Field(default=None, ge=0)


class Descarte(BaseModel):
    motivo: str | None = Field(default=None, max_length=20)


class TurnoGuia(BaseModel):
    rol: Literal["usuario", "guia"]
    texto: str = Field(max_length=4000)


class PreguntaGuia(BaseModel):
    texto: str = Field(max_length=8000)
    vista: Literal["mapa", "registro"] = "mapa"
    # La conversación anterior la guarda el navegador; llega como texto NO confiable
    historial: list[TurnoGuia] = Field(default_factory=list, max_length=20)
