from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from app.application.rat.casos_uso.generar_informe import FORMATOS


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmitirEntrada(_Base):
    forzar: bool = Field(False, description="Emitir aunque el registro no haya cambiado desde la última emisión")


class EnviarEntrada(_Base):
    email: str | None = Field(None, max_length=100, description="Vacío = el correo del usuario de la empresa")
    formatos: list[str] = Field(default_factory=lambda: list(FORMATOS), min_length=1, max_length=2)
