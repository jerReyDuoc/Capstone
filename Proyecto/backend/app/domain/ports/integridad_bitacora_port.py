"""Puerto de integridad de la bitácora: sellado por lotes, verificación y recorrido ordenado de audit_log."""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Protocol


class IntegridadBitacoraPort(Protocol):
    def sello_dict(self, s: Any) -> dict: ...

    async def sellar_pendientes(self, session: Any, tamano: int | None = None,
                                ahora: datetime | None = None) -> list[Any]: ...

    async def listar_sellos(self, session: Any, page: int = 1, size: int = 50) -> tuple[list[Any], int]: ...

    async def sellos_que_cubren(self, session: Any, desde: datetime | None,
                                hasta: datetime | None) -> list[Any]: ...

    async def verificar_lotes(self, session: Any, bloque: int = 1000) -> dict: ...

    def filas_en_orden(self, session: Any, desde_id: int = 0, hasta_id: int | None = None,
                       lote: int = 1000) -> AsyncIterator[Any]: ...
