from pydantic import BaseModel, Field


class CambioRetencion(BaseModel):
    modo: str = Field(..., max_length=20)
    plazo_titular_dias: int | None = None


class PedidoEjecucion(BaseModel):
    confirmar: bool = False
