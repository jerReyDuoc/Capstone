"""Adaptador de `IntegridadBitacoraPort`: delega en lotes_bitacora y bitacora_cadena."""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from app.infrastructure.repositories import lotes_bitacora
from app.infrastructure.repositories import bitacora_cadena


class IntegridadBitacora:
    def sello_dict(self, s: Any) -> dict:
        return lotes_bitacora.sello_dict(s)

    async def sellar_pendientes(self, session: Any, tamano: int | None = None,
                                ahora: datetime | None = None) -> list[Any]:
        return await lotes_bitacora.sellar_pendientes(session, tamano, ahora)

    async def listar_sellos(self, session: Any, page: int = 1, size: int = 50) -> tuple[list[Any], int]:
        return await lotes_bitacora.listar_sellos(session, page, size)

    async def sellos_que_cubren(self, session: Any, desde: datetime | None, hasta: datetime | None) -> list[Any]:
        return await lotes_bitacora.sellos_que_cubren(session, desde, hasta)

    async def verificar_lotes(self, session: Any, bloque: int = 1000) -> dict:
        return await lotes_bitacora.verificar_lotes(session, bloque)

    def filas_en_orden(self, session: Any, desde_id: int = 0, hasta_id: int | None = None,
                       lote: int = 1000) -> AsyncIterator[Any]:
        return bitacora_cadena.filas_en_orden(session, desde_id, hasta_id, lote)
