from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MandanteEntrada(_Base):
    clave: str = Field(..., min_length=1, max_length=150, description="Clave de la organización (la entrega el GET)")
    direccion: str | None = Field(None, max_length=200)
    correo: str | None = Field(None, max_length=100)
    dpo: str | None = Field(None, max_length=150, description="Correo o cargo del delegado de protección de datos")


class DatosEntrada(_Base):
    direccion: str | None = Field(None, max_length=200)
    correo: str | None = Field(None, max_length=100)
    telefono: str | None = Field(None, max_length=25)
    tiene_dpo: bool | None = None
    dpo_cargo: str | None = Field(None, max_length=120)
    dpo_correo: str | None = Field(None, max_length=100)
    mandantes: list[MandanteEntrada] | None = Field(None, max_length=100)


class EmitirEntrada(_Base):
    partes: list[str] = Field(default_factory=list, max_length=2,
                              description="responsable, encargado o ambas (vacío = todas las que tienen actividades)")
    forzar: bool = Field(False, description="Emitir aunque nada haya cambiado desde la última emisión")
