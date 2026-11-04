"""
HU-24 · Contenido de las versiones PUBLICADAS de la matriz, en memoria.

Una versión publicada (o reemplazada) no cambia nunca (trigger en PostgreSQL), así que su
contenido se puede guardar sin expiración. Lo usan las evaluaciones cerradas: su informe,
su plan formativo y el recálculo por remediación (HU-17) leen la versión con que se
respondieron, no la vigente.
"""
from __future__ import annotations

from collections import OrderedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.matriz.contenido import ArbolAplicabilidad, arbol

_MAXIMO = 32
_contenidos: "OrderedDict[int, dict]" = OrderedDict()
_arboles: dict[int, ArbolAplicabilidad] = {}


def invalidar() -> None:
    _contenidos.clear()
    _arboles.clear()


async def contenido_de_version(session: AsyncSession, version_id: int | None) -> dict | None:
    """Contenido de una versión publicada o reemplazada (None si no existe o es borrador)."""
    if not version_id:
        return None
    if version_id in _contenidos:
        _contenidos.move_to_end(version_id)
        return _contenidos[version_id]
    from app.domain.models.matriz_version import ESTADO_BORRADOR, MatrizVersion

    v = await session.get(MatrizVersion, int(version_id))
    if v is None or v.estado == ESTADO_BORRADOR:
        return None
    _contenidos[version_id] = v.contenido
    while len(_contenidos) > _MAXIMO:
        viejo, _ = _contenidos.popitem(last=False)
        _arboles.pop(viejo, None)
    return v.contenido


async def arbol_de_version(session: AsyncSession, version_id: int) -> ArbolAplicabilidad | None:
    if version_id in _arboles:
        return _arboles[version_id]
    contenido = await contenido_de_version(session, version_id)
    if contenido is None:
        return None
    a = arbol(contenido)
    _arboles[version_id] = a
    return a
