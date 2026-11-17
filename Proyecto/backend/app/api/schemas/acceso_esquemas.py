from typing import Literal
from pydantic import BaseModel, Field


class InicioSesionAdminRequest(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


class AccesoTitularRequest(BaseModel):
    usuario_temporal_id: int
    email: str


class AccesoEncuestadoRequest(BaseModel):
    evaluacion_id: int
    clave: str


class GenerarClaveRequest(BaseModel):
    evaluacion_id: int


class InicioSesionClienteRequest(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


class VerificarActivacionRequest(BaseModel):
    token: str = Field(..., max_length=200)


class ActivarCuentaRequest(BaseModel):
    token: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


class SolicitarRecuperacionRequest(BaseModel):
    tipo: Literal["cliente", "admin"] = "cliente"
    email: str = Field(..., max_length=200)


class VerificarRecuperacionRequest(BaseModel):
    token: str = Field(..., max_length=200)


class RestablecerRequest(BaseModel):
    token: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)
