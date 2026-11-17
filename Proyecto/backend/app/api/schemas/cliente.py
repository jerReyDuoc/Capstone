from pydantic import BaseModel, Field


class ArchivarInformeRequest(BaseModel):
    evaluacion_id: int = Field(..., ge=1)
