from pydantic import BaseModel, Field


class ConsentimientoRequest(BaseModel):
    version: str = Field(..., max_length=20)
    aceptado: bool


class CrearSolicitudRequest(BaseModel):
    evaluacion_id: int = Field(..., ge=1)
    nombre: str = Field(..., max_length=200)
    cargo: str = Field(..., max_length=200)
    empresa: str = Field(..., max_length=200)
    email: str = Field(..., max_length=200)
    telefono: str | None = Field(None, max_length=40)
    consentimiento_contacto: ConsentimientoRequest
    consentimiento_migracion: ConsentimientoRequest
    captcha_token: str = Field("", max_length=2048)
