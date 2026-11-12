"""
HU-35 criterio 4 · Estados de una actividad: borrador → en revisión → vigente → archivada.

Decisiones del PO (11-nov):
  - Aprueba el mismo usuario de la empresa (en revisión → vigente).
  - Editar una actividad vigente abre una NUEVA versión en borrador; la vigente anterior sigue
    valiendo (rat_actividad.version_vigente) hasta que la nueva quede vigente.
  - Un cambio en el mapa que la afecta la devuelve AUTOMÁTICAMENTE a "en revisión".
  - Una archivada se reactiva sin duplicarla: vuelve a borrador si nunca estuvo vigente y, si no,
    a "en revisión" para confirmar que sigue al día (aprobarla sin cambios no crea otra versión).

Acciones:
  enviar_revision   borrador     → en_revision
  volver_borrador   en_revision  → borrador
  aprobar           en_revision  → vigente      (sin campos obligatorios vacíos)
  nueva_version     vigente      → borrador     (la versión vigente se conserva)
  archivar          borrador | en_revision | vigente → archivada
  reactivar         archivada    → borrador | en_revision
"""
from __future__ import annotations

from app.domain.rat.catalogo import ARCHIVADA, BORRADOR, EN_REVISION, VIGENTE

ACCIONES = ("enviar_revision", "volver_borrador", "aprobar", "nueva_version", "archivar", "reactivar")

_DESDE = {
    "enviar_revision": {BORRADOR},
    "volver_borrador": {EN_REVISION},
    "aprobar": {EN_REVISION},
    "nueva_version": {VIGENTE},
    "archivar": {BORRADOR, EN_REVISION, VIGENTE},
    "reactivar": {ARCHIVADA},
}

ETIQUETA_ACCION = {
    "enviar_revision": "Enviar a revisión",
    "volver_borrador": "Volver a borrador",
    "aprobar": "Dejar vigente",
    "nueva_version": "Editar en una nueva versión",
    "archivar": "Archivar",
    "reactivar": "Reactivar",
}

# Estados en que la actividad se puede editar (vigente y archivada no: hay que abrir una versión
# nueva o reactivarla primero).
EDITABLES = frozenset({BORRADOR, EN_REVISION})


class TransicionInvalida(ValueError):
    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje = mensaje


_MENSAJES_NO_PERMITIDA = {
    "enviar_revision": "Solo un borrador se puede enviar a revisión.",
    "volver_borrador": "Solo una actividad en revisión puede volver a borrador.",
    "aprobar": "Para dejarla vigente, primero envíala a revisión.",
    "nueva_version": "Solo una actividad vigente se edita en una nueva versión.",
    "archivar": "La actividad ya está archivada.",
    "reactivar": "Solo una actividad archivada se puede reactivar.",
}


def acciones_disponibles(estado: str) -> list[str]:
    return [a for a in ACCIONES if estado in _DESDE[a]]


def destino(accion: str, estado: str, estado_previo: str | None = None, tuvo_vigente: bool = False) -> str:
    """Estado al que pasa la actividad con `accion`, o TransicionInvalida."""
    if accion not in _DESDE:
        raise TransicionInvalida("Esa acción no existe.")
    if estado not in _DESDE[accion]:
        raise TransicionInvalida(_MENSAJES_NO_PERMITIDA[accion])
    if accion == "enviar_revision":
        return EN_REVISION
    if accion in ("volver_borrador", "nueva_version"):
        return BORRADOR
    if accion == "aprobar":
        return VIGENTE
    if accion == "archivar":
        return ARCHIVADA
    # reactivar
    if tuvo_vigente or estado_previo in (EN_REVISION, VIGENTE):
        return EN_REVISION
    return BORRADOR


def tras_cambio_en_mapa(estado: str) -> str:
    """El mapa cambió algo que la actividad usa: la vigente vuelve a revisión; las demás siguen igual."""
    return EN_REVISION if estado == VIGENTE else estado
