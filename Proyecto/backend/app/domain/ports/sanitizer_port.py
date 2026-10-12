"""
Puerto del sanitizador de datos personales (Ley 21.719).

Reglas de negocio que cualquier implementación debe respetar:
- Las etiquetas son FIJAS por tipo ([RUT_ANON], nunca [RUT_1], [RUT_2]...).
- Si la sanitización no puede garantizarse (motor NER ausente, excepción interna),
  se lanza `SanitizacionError`: es preferible fallar que filtrar PII.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class TipoEntidad(str, Enum):
    RUT = "RUT"
    NOMBRE = "NOMBRE"
    CORREO = "CORREO"
    TELEFONO = "TEL"
    DIRECCION = "DIRECCION"
    CODIFICADO = "DATO_CODIFICADO"

    @property
    def etiqueta(self) -> str:
        return f"[{self.value}_ANON]"


ETIQUETAS = {t.etiqueta for t in TipoEntidad}


@dataclass(frozen=True)
class EntidadDetectada:
    """Una entidad encontrada. `inicio`/`fin` son offsets sobre el texto NORMALIZADO."""
    tipo: TipoEntidad
    valor: str
    inicio: int
    fin: int
    fuente: str  # "regex" | "ner" | "regex+ner" | "decodificado"


@dataclass
class ResultadoSanitizacion:
    texto: str                                   # lo único que puede salir hacia el LLM
    entidades: list[EntidadDetectada] = field(default_factory=list)
    motor: str = ""                              # versión del motor (auditoría)
    truncado: bool = False
    duracion_ms: float = 0.0

    def conteo_por_tipo(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for e in self.entidades:
            conteo[e.tipo.value] = conteo.get(e.tipo.value, 0) + 1
        return conteo


class SanitizacionError(RuntimeError):
    """La sanitización falló: el texto NO debe enviarse al LLM."""


class SanitizerPort(ABC):
    @abstractmethod
    def sanitizar(self, texto: str, max_chars: int | None = None) -> ResultadoSanitizacion:
        """
        Detecta y reemplaza PII por etiquetas fijas.
        Si `max_chars` se indica, el recorte se hace DESPUÉS de detectar, de modo que
        nunca quede un dato personal cortado a medias fuera del alcance de las regex.
        Lanza SanitizacionError ante cualquier fallo.
        """
        ...
