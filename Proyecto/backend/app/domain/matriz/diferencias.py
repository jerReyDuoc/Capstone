"""
HU-24 · Qué cambia entre dos versiones de la matriz (lógica pura).

Se usa para mostrar el borrador frente a la versión vigente antes de publicar, para el
historial de versiones y para el detalle del audit log al publicar.
"""
from __future__ import annotations

from typing import Mapping

from app.domain.matriz.contenido import CAMPOS, ENTIDADES, ORDEN_ENTIDADES, etiqueta, por_id


def _iguales(a, b) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return sorted(a or []) == sorted(b or [])
    return a == b


def diferencias(antes: Mapping, despues: Mapping) -> dict:
    """
    {
      "total": n,
      "controles": {"nuevos": [...], "modificados": [...], "retirados": [...], "restaurados": [...]},
      ...
    }
    Cada elemento: {id, etiqueta, campos: [nombres de campo cambiados]}.
    """
    salida: dict = {"total": 0}
    for entidad in ORDEN_ENTIDADES:
        clave_activo = ENTIDADES[entidad]["activo"]
        a, d = por_id(antes, entidad), por_id(despues, entidad)
        grupo = {"nuevos": [], "modificados": [], "retirados": [], "restaurados": []}
        for item_id, nuevo in sorted(d.items()):
            viejo = a.get(item_id)
            ficha = {"id": item_id, "etiqueta": etiqueta(entidad, nuevo)}
            if viejo is None:
                grupo["nuevos"].append({**ficha, "campos": []})
                continue
            activo_antes, activo_despues = bool(viejo.get(clave_activo, True)), bool(nuevo.get(clave_activo, True))
            campos = [k for k in CAMPOS[entidad] if not _iguales(viejo.get(k), nuevo.get(k))]
            if activo_antes and not activo_despues:
                grupo["retirados"].append({**ficha, "campos": campos})
            elif not activo_antes and activo_despues:
                grupo["restaurados"].append({**ficha, "campos": campos})
            elif campos:
                grupo["modificados"].append({**ficha, "campos": campos})
        # Un elemento que estaba y ya no está (solo pasa si alguien editó el JSON a mano)
        for item_id, viejo in sorted(a.items()):
            if item_id not in d and bool(viejo.get(clave_activo, True)):
                grupo["retirados"].append({"id": item_id, "etiqueta": etiqueta(entidad, viejo), "campos": []})
        salida[entidad] = grupo
        salida["total"] += sum(len(v) for v in grupo.values())
    return salida


def conteo(dif: Mapping) -> dict:
    """Versión corta para el audit log: {"controles": {"nuevos": 1, ...}, ...} (sin ceros)."""
    salida = {}
    for entidad in ORDEN_ENTIDADES:
        grupo = {k: len(v) for k, v in (dif.get(entidad) or {}).items() if v}
        if grupo:
            salida[entidad] = grupo
    return salida


def estado_de(dif: Mapping, entidad: str) -> dict[int, str]:
    """{id: nuevo|modificado|retirado|restaurado} para pintar la tabla del mantenedor."""
    nombres = {"nuevos": "nuevo", "modificados": "modificado", "retirados": "retirado", "restaurados": "restaurado"}
    salida = {}
    for grupo, items in (dif.get(entidad) or {}).items():
        for x in items:
            salida[int(x["id"])] = nombres[grupo]
    return salida
