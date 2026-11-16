"""Puerto del limitador de contadores con ventana fija (límites contra abuso, HU-19)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LimitadorNoDisponibleError(Exception):
    pass


@dataclass(frozen=True)
class Consumo:
    permitido: bool
    usados: int
    limite: int
    reintentar_en_s: int

    @property
    def restantes(self) -> int:
        return max(0, self.limite - self.usados)


class Limitador(Protocol):
    async def consumir(self, clave: str, limite: int, ventana_s: int) -> Consumo: ...
    async def devolver(self, clave: str) -> None: ...
    async def usados(self, clave: str) -> int: ...
    async def restante_s(self, clave: str) -> int: ...
    async def reiniciar(self, clave: str) -> None: ...
