from typing import Any
from pydantic import BaseModel, Field


class CrearBorradorRequest(BaseModel):
    desde_version_id: int | None = Field(None, ge=1, description="Versión de origen (por defecto, la vigente)")


class RevisionRequest(BaseModel):
    revision: int | None = Field(None, ge=1)


class DatosRequest(RevisionRequest):
    datos: dict[str, Any] = Field(..., description="Campos del elemento (ver app/domain/matriz/contenido.py)")


class AplicabilidadRequest(RevisionRequest):
    aplica_siempre: bool = False
    filtros: list[int] = Field(default_factory=list, max_length=50)


class PublicarRequest(RevisionRequest):
    etiqueta: str = Field(..., max_length=30)
    nota_cambio: str = Field(..., max_length=1000)
