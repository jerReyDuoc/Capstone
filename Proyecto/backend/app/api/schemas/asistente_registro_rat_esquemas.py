from __future__ import annotations

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
