from pydantic import BaseModel, Field


class RubroRequest(BaseModel):
    nombre: str = Field(..., max_length=200)
