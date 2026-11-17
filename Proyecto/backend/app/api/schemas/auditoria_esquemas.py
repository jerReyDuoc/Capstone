from pydantic import BaseModel, Field


# ------------------------------------------------------------------ admin: cuentas de auditor
class CrearAuditorRequest(BaseModel):
    email: str = Field(..., max_length=100)
    organizacion: str = Field(..., max_length=120)
    password: str = Field(..., max_length=200)
    dias_vigencia: int = Field(30, ge=1, le=365)


class ActualizarAuditorRequest(BaseModel):
    activo: bool | None = None
    dias_vigencia: int | None = Field(None, ge=1, le=365)
    password: str | None = Field(None, max_length=200)
