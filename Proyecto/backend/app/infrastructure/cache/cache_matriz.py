"""Adaptador de `CacheMatrizPort`: delega en los módulos de caché de la matriz."""
from __future__ import annotations

from typing import Any

from app.domain.matriz.contenido import ArbolAplicabilidad
from app.infrastructure.cache import arbol_aplicabilidad, catalogo_controles, versiones_matriz


class CacheMatriz:
    async def catalogo(self, session: Any) -> Any:
        return await catalogo_controles.obtener(session)

    async def arbol_vigente(self, session: Any) -> ArbolAplicabilidad:
        return await arbol_aplicabilidad.arbol_vigente(session)

    async def arbol_de_version(self, session: Any, version_id: int) -> ArbolAplicabilidad | None:
        return await versiones_matriz.arbol_de_version(session, version_id)

    async def contenido_de_version(self, session: Any, version_id: int | None) -> dict | None:
        return await versiones_matriz.contenido_de_version(session, version_id)

    def invalidar(self) -> None:
        catalogo_controles.invalidar()
        arbol_aplicabilidad.invalidar()
