"""
Puerto de auditoría de la capa de IA: métricas de cada llamada y mapa de entidades.
Los DTOs son dataclasses simples para que la capa de aplicación no dependa de SQLAlchemy.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.ports.sanitizer_port import EntidadDetectada


@dataclass
class ContextoLlamada:
    """Para qué entidad de negocio se hace la llamada (trazabilidad)."""
    evaluacion_id: int | None = None
    respuesta_id: int | None = None
    evidencia_id: int | None = None


@dataclass
class RegistroSanitizacion:
    campo: str                         # "evidencia" | "justificacion" | ...
    entidades: list[EntidadDetectada]
    motor: str
    duracion_ms: float
    truncado: bool
    contexto: ContextoLlamada
    traza_id: str                      # une la sanitización con su llamada al LLM


@dataclass
class RegistroLlamada:
    tarea: str
    proveedor: str
    modelo: str
    prompt_version: str
    exito: bool
    contexto: ContextoLlamada
    fecha: datetime
    traza_id: str
    tipo_error: str | None = None
    detalle_error: str | None = None   # nunca contiene texto del usuario
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    costo_estimado_usd: float | None = None
    latencia_ms: float | None = None
    sanitizado: bool = True
    entidades_anonimizadas: int = 0
    clasificacion: str | None = None
    confianza: float | None = None
    advertencias: list[str] = field(default_factory=list)


class RegistroIAPort(ABC):
    @abstractmethod
    async def guardar_llamada(self, registro: RegistroLlamada) -> int:
        """Guarda la métrica y devuelve su id."""
        ...

    @abstractmethod
    async def guardar_sanitizaciones(self, registros: list[RegistroSanitizacion]) -> None:
        """Guarda el mapa de entidades (cifrado). Debe lanzar excepción si falla."""
        ...
