from pydantic import BaseModel


class MarcarPruebaRequest(BaseModel):
    es_prueba: bool
