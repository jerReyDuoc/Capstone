"""
HU-24 · Árbol de aplicabilidad vigente, en memoria.

El cuestionario lo consulta en cada petición (controles aplicables, progreso, respuestas),
así que se carga una vez por proceso y se reutiliza. Se recarga:

  - al publicar una versión de la matriz en ESTE proceso (invalidar()), y
  - cuando otro proceso (otro worker de uvicorn o el worker arq) publicó: cada
    VERIFICAR_CADA_SEGUNDOS se mira, con una consulta mínima, qué versión está publicada
    (version_vigente_id). Si cambió, se recargan este árbol y el catálogo de controles.

Sin reglas en la BD (BD nueva o la SQLite de las pruebas) se usa la semilla de
control_tree.py, igual que antes de HU-24.
"""
from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.filters.control_tree import ARBOL_POR_DEFECTO
from app.domain.matriz.contenido import ArbolAplicabilidad

VERIFICAR_CADA_SEGUNDOS = 15.0

_SIN_DATO = object()
_marca: dict = {"version_id": _SIN_DATO, "verificado_en": 0.0}
_arbol: dict = {"arbol": None, "version_id": _SIN_DATO}


def invalidar() -> None:
    """Fuerza a releer la versión vigente y el árbol en la próxima petición de este proceso."""
    _marca["version_id"] = _SIN_DATO
    _marca["verificado_en"] = 0.0
    _arbol["arbol"] = None
    _arbol["version_id"] = _SIN_DATO


async def version_vigente_id(session: AsyncSession) -> int | None:
    """Id de la versión publicada, releído como máximo cada VERIFICAR_CADA_SEGUNDOS."""
    ahora = time.monotonic()
    if _marca["version_id"] is not _SIN_DATO and ahora - _marca["verificado_en"] < VERIFICAR_CADA_SEGUNDOS:
        return _marca["version_id"]
    from app.domain.models.matriz_version import ESTADO_PUBLICADA, MatrizVersion

    vid = (await session.execute(
        select(MatrizVersion.id).where(MatrizVersion.estado == ESTADO_PUBLICADA)
    )).scalar_one_or_none()
    _marca["version_id"] = vid
    _marca["verificado_en"] = ahora
    return vid


async def cargar(session: AsyncSession) -> ArbolAplicabilidad:
    """Lee el árbol de la BD (sin caché): reglas de controles activos y compuertas activas."""
    from app.domain.models.matriz_control import MatrizControl
    from app.domain.models.matriz_version import ReglaAplicabilidad
    from app.domain.models.pregunta_filtro import PreguntaFiltro

    filas = (await session.execute(
        select(MatrizControl.codigo_control, PreguntaFiltro.codigo, PreguntaFiltro.activa)
        .select_from(ReglaAplicabilidad)
        .join(MatrizControl, MatrizControl.id_control == ReglaAplicabilidad.control_id)
        .outerjoin(PreguntaFiltro, PreguntaFiltro.id_pregunta == ReglaAplicabilidad.pregunta_filtro_id)
        .where(MatrizControl.activo.is_(True))
    )).all()
    if not filas:
        return ARBOL_POR_DEFECTO
    compuertas = frozenset((await session.execute(
        select(PreguntaFiltro.codigo).where(PreguntaFiltro.activa.is_(True), PreguntaFiltro.es_compuerta.is_(True))
    )).scalars().all())
    base: set[str] = set()
    por_filtro: dict[str, set[str]] = {}
    for control, filtro, filtro_activo in filas:
        if not control:
            continue
        if filtro is None:
            base.add(control)
        elif filtro_activo:
            por_filtro.setdefault(filtro, set()).add(control)
    return ArbolAplicabilidad(
        compuertas=compuertas, base=frozenset(base),
        por_filtro={k: frozenset(v) for k, v in por_filtro.items()},
    )


async def arbol_vigente(session: AsyncSession) -> ArbolAplicabilidad:
    vid = await version_vigente_id(session)
    if _arbol["arbol"] is not None and _arbol["version_id"] == vid:
        return _arbol["arbol"]
    arbol = await cargar(session)
    _arbol["arbol"] = arbol
    _arbol["version_id"] = vid
    return arbol
