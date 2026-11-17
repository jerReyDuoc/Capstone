from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------- correo
class EnviarInformeRequest(BaseModel):
    # Encuestado: vacío = el correo que registró. Equipo interno: obligatorio.
    email: str | None = Field(None, max_length=100)
    # true = además guardarlo como su correo (HU-19: retomar / recibir informes)
    recordar: bool = False
    severidad: str | None = Field(None, max_length=80)
    dominio: str | None = Field(None, max_length=80)
    estado: str | None = Field(None, max_length=30)
    q: str | None = Field(None, max_length=80)
