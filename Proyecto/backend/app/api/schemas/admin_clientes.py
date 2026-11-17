from datetime import date
from pydantic import BaseModel, Field


# ------------------------------------------------------------------ esquemas
class CambiarEstadoRequest(BaseModel):
    estado: str = Field(..., max_length=20)


class EmpresaRequest(BaseModel):
    razon_social: str = Field(..., max_length=200)
    rut: str = Field(..., max_length=20)
    rubro_id: int = Field(..., ge=1)
    fecha_inicio_contrato: date
    fecha_termino_contrato: date


class UsuarioRequest(BaseModel):
    nombre: str = Field(..., max_length=200)
    email: str = Field(..., max_length=200)


class AltaEmpresaRequest(BaseModel):
    empresa: EmpresaRequest
    usuario: UsuarioRequest
    solicitudes_ids: list[int] = Field(..., min_length=1, max_length=20)


class AsociarRequest(BaseModel):
    solicitudes_ids: list[int] = Field(..., min_length=1, max_length=20)


class RenovacionRequest(BaseModel):
    fecha_termino_contrato: date


class MotivoContratoRequest(BaseModel):
    motivo: str = Field(..., max_length=30, description="no_pago | solicitud_cliente | incumplimiento | "
                                                          "fin_acuerdo | otro")
