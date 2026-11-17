from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmitirEntrada(_Base):
    tipo: str = Field(..., pattern="^(rat|ropa)$")
    forzar: bool = False


class DatosRopaEntrada(_Base):
    direccion: str | None = Field(None, max_length=200)
    correo: str | None = Field(None, max_length=100)
    telefono: str | None = Field(None, max_length=25)
    tiene_dpo: bool | None = None
    dpo_cargo: str | None = Field(None, max_length=120)
    dpo_correo: str | None = Field(None, max_length=100)
