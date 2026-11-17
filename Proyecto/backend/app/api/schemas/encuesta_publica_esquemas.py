from pydantic import BaseModel, Field


class AvisoLegalAceptado(BaseModel):
    version: str = Field(..., max_length=20)
    aceptado: bool


class IniciarEncuestaRequest(BaseModel):
    rubro_id: int = Field(..., ge=1)
    aviso_legal: AvisoLegalAceptado
    captcha_token: str = Field("", max_length=2048)


class EmailOpcionalRequest(BaseModel):
    # null = borrar el email registrado
    email: str | None = Field(None, max_length=100)
