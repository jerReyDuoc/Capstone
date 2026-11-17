from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VerificacionEntrada(_Base):
    clave: str = Field(..., min_length=3, max_length=40, pattern=r"^(actividad|elemento|flujo):\d{1,9}$")
    criterios: list[str] | None = Field(None, max_length=10, description="Vacío = todos los puntos que aplican")
    decision: Literal["verificado", "aceptado", "pendiente"]
    nota: str | None = Field(None, max_length=1000)


class ObservacionEntrada(_Base):
    clave: str = Field(..., min_length=3, max_length=40, pattern=r"^(actividad|elemento|flujo|registro):\d{1,9}$")
    criterio: str | None = Field(None, max_length=40)
    prioridad: Literal["alta", "media", "baja"] = "media"
    texto: str = Field(..., min_length=1, max_length=1000)


class CierreEntrada(_Base):
    nota: str = Field(..., min_length=1, max_length=1000)


class MarcaEntrada(_Base):
    revisor_nombre: str = Field(..., min_length=1, max_length=120)
    revisor_cargo: str | None = Field(None, max_length=120)
    conclusion: str | None = Field(None, max_length=1500)
    huella: str | None = Field(None, min_length=64, max_length=64, description="La huella del registro que se revisó")
    confirmo: bool = False


class ConfiguracionEntrada(_Base):
    plazo_meses: int = Field(..., ge=1, le=36)
    aviso_dias: int = Field(..., ge=0, le=90)
    recordatorio_correo: bool = True


class EnvioEntrada(_Base):
    email: str | None = Field(None, max_length=100, description="Vacío = el correo del usuario de la empresa")
    con_paquete: bool = False
