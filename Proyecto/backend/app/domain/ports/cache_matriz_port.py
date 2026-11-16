"""Puerto de la caché de matriz: catálogo de controles, árbol de aplicabilidad y versiones."""
from __future__ import annotations

from typing import Any, Protocol

from app.domain.matriz.contenido import ArbolAplicabilidad


class CacheMatrizPort(Protocol):
    async def catalogo(self, session: Any) -> Any: ...

    async def arbol_vigente(self, session: Any) -> ArbolAplicabilidad: ...

    async def arbol_de_version(self, session: Any, version_id: int) -> ArbolAplicabilidad | None: ...

    async def contenido_de_version(self, session: Any, version_id: int | None) -> dict | None: ...

    def invalidar(self) -> None: ...
