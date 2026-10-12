"""
Puerto genérico hacia un proveedor de LLM.

El proveedor SOLO transporta: recibe mensajes ya sanitizados y un schema Pydantic,
devuelve el objeto validado + uso de tokens. No conoce prompts, reglas de negocio
ni la BD. Cambiar Groq por otro proveedor = escribir otro adaptador de este puerto.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class TipoErrorLLM(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTENTICACION = "autenticacion"
    CONEXION = "conexion"
    PROVEEDOR = "proveedor"            # 5xx u otro error del servicio
    SALIDA_INVALIDA = "salida_invalida"  # no cumple el schema
    DESCONOCIDO = "desconocido"


@dataclass
class LLMRequest(Generic[T]):
    system: str
    user: str
    schema: type[T]
    modelo: str | None = None          # None = modelo por defecto del proveedor
    temperatura: float = 0.0
    max_tokens_salida: int = 1500
    timeout_s: float = 60.0


@dataclass
class LLMResponse(Generic[T]):
    data: T
    proveedor: str
    modelo: str
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    latencia_ms: float = 0.0


class LLMProviderError(Exception):
    def __init__(self, tipo: TipoErrorLLM, mensaje: str, latencia_ms: float = 0.0):
        super().__init__(mensaje)
        self.tipo = tipo
        self.latencia_ms = latencia_ms


class LLMProviderPort(ABC):
    nombre: str = "desconocido"
    modelo_por_defecto: str = ""

    @abstractmethod
    async def generar(self, request: LLMRequest[T]) -> LLMResponse[T]:
        """Lanza LLMProviderError (con su tipo) ante cualquier fallo."""
        ...
