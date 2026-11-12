"""
HU-35 criterio 2 · Qué actividades del registro afecta un cambio en el mapa de datos.

El mapa (HU-34) describe cada cambio como una lista de diferencias entre la instantánea anterior y la
nueva: [{entidad: elemento|flujo, operacion: creado|editado|eliminado, id, nombre, campos}]. Una
actividad queda afectada cuando:
  - se editó o eliminó un elemento o un flujo que eligió;
  - se editó o eliminó un elemento que es extremo de un flujo que eligió (por ejemplo, cambió el
    país de un tercero y la transferencia cambia).
Lo que solo cambia la marca "por confirmar" del mapa no afecta. Lo nuevo tampoco: la actividad no
lo eligió todavía.
"""
from __future__ import annotations

from app.domain.mapa_datos.versiones import ETIQUETA_CAMPO, NOMBRE_TIPO

_IGNORADOS = frozenset({"pendiente_revision"})


def cambios_relevantes(cambios: list[dict]) -> list[dict]:
    salida = []
    for c in cambios:
        if c.get("operacion") == "creado":
            continue
        if c.get("operacion") == "editado" and not (set(c.get("campos") or []) - _IGNORADOS):
            continue
        salida.append(c)
    return salida


def _extremos(instantanea: dict | None) -> dict[int, tuple[int, int]]:
    return {f["id"]: (f["origen_id"], f["destino_id"]) for f in (instantanea or {}).get("flujos", [])}


def motivo(c: dict) -> str:
    """Texto legible del cambio, para mostrarlo en la actividad."""
    nombre = c.get("nombre") or "un registro"
    if c["entidad"] == "elemento":
        sujeto = f"{NOMBRE_TIPO.get(c.get('tipo') or '', 'el elemento')} «{nombre}»"
    else:
        sujeto = f"el flujo «{nombre}»"
    if c["operacion"] == "eliminado":
        return f"Se eliminó del mapa {sujeto}."
    campos = [ETIQUETA_CAMPO.get(x, x) for x in (c.get("campos") or []) if x not in _IGNORADOS]
    detalle = f" ({', '.join(campos[:4])}{'…' if len(campos) > 4 else ''})" if campos else ""
    return f"Cambió en el mapa {sujeto}{detalle}."


def afectadas(actividades: list[dict], cambios: list[dict], antes: dict | None, despues: dict | None) -> dict[int, list[str]]:
    """
    `actividades`: [{id, contenido}] (no archivadas). Devuelve {actividad_id: [motivos]} de las afectadas.
    """
    relevantes = cambios_relevantes(cambios)
    if not relevantes:
        return {}
    extremos = {**_extremos(antes), **_extremos(despues)}
    salida: dict[int, list[str]] = {}
    for a in actividades:
        contenido = a.get("contenido") or {}
        els = {x.get("id") for x in contenido.get("elementos") or []}
        fls = {x.get("id") for x in contenido.get("flujos") or []}
        extremos_elegidos = {e for f in fls for e in extremos.get(f, ())}
        motivos: list[str] = []
        for c in relevantes:
            if c["entidad"] == "elemento":
                toca = c["id"] in els or c["id"] in extremos_elegidos
            else:
                toca = c["id"] in fls
            if toca:
                m = motivo(c)
                if m not in motivos:
                    motivos.append(m)
        if motivos:
            salida[a["id"]] = motivos
    return salida
