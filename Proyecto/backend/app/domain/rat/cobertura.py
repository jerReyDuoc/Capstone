"""
HU-39 criterio 2 · Cobertura del mapa por el registro: flujos del mapa que no pertenecen a ninguna actividad.

Un flujo del mapa (datos que viajan entre sistemas o hacia un tercero) siempre ocurre por alguna razón:
si ninguna actividad del RAT lo elige, falta registrar esa actividad o el flujo sobra. Lo usan el
asistente (inconsistencia "flujo_sin_actividad") y cualquier vista del registro.

Puro y determinista: mismo mapa y mismas actividades, mismo resultado. Las actividades archivadas no
cubren nada (ya no se realizan).
"""
from __future__ import annotations

from app.domain.mapa_datos.modelo import Flujo
from app.domain.rat.modelo import completar

ARCHIVADA = "archivada"


def flujos_cubiertos(actividades: list[dict]) -> set[int]:
    """Ids de flujos elegidos por alguna actividad no archivada. `actividades`: [{"estado", "contenido"}]."""
    cubiertos: set[int] = set()
    for a in actividades:
        if a.get("estado") == ARCHIVADA:
            continue
        cubiertos |= {x["id"] for x in completar(a.get("contenido"))["flujos"]}
    return cubiertos


def flujos_sin_actividad(flujos: list[Flujo], actividades: list[dict]) -> list[Flujo]:
    """Los flujos del mapa que ninguna actividad vigente, en borrador o en revisión elige (en orden de id)."""
    cubiertos = flujos_cubiertos(actividades)
    return [f for f in sorted(flujos, key=lambda f: f.id or 0) if f.id not in cubiertos]
