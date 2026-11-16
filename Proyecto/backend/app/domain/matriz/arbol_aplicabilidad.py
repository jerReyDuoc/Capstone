"""
Árbol de decisión para determinar qué controles aplican a una organización.

La lógica es secuencial y aditiva:
- F1 es la compuerta principal: si es NO, no aplica ningún control.
- F2..F7 suman controles adicionales al set base si la respuesta es SI.
- El set base (22 controles) aplica siempre que F1 sea SI.

HU-24: el árbol ya no se edita aquí. Vive en la BD (tabla regla_aplicabilidad y
preguntas_filtro.es_compuerta) y el administrador lo cambia desde el mantenedor de la
matriz, con versionado. Las constantes de abajo son la SEMILLA de la versión inicial (la
migración f8c2a6d4e1b7 las copia a la BD) y el respaldo cuando la tabla está vacía (p. ej.
la BD SQLite de las pruebas). En ejecución se usa app/infrastructure/cache/arbol_aplicabilidad.py.
"""
from typing import Mapping

from app.domain.matriz.contenido import ArbolAplicabilidad


# Controles que aplican a TODA organización que usa IA (F1=SI)
CONTROLES_BASE = [
    "DAT-001", "DAT-003", "DAT-004", "DAT-005", "DAT-006", "DAT-010",
    "GOB-001", "GOB-002", "GOB-003", "GOB-004", "GOB-005", "GOB-007",
    "GOB-009", "GOB-010",
    "RIE-001", "RIE-003", "RIE-004", "RIE-008", "RIE-010",
    "SEG-006", "SEG-007", "SEG-009",
]

# Controles que se suman según la respuesta de cada filtro
CONTROLES_POR_FILTRO = {
    "F2": ["DAT-002", "DAT-009"],
    "F3": ["DAT-007", "DAT-008", "GOB-008", "SEG-008"],
    "F4": ["RIE-002", "SEG-001", "SEG-002", "SEG-005"],
    "F5": ["RIE-009", "SEG-003", "SEG-004"],
    "F6": ["RIE-005", "RIE-006", "SEG-010"],
    "F7": ["RIE-007", "GOB-006"],
}


# Árbol de respaldo (semilla): F1 es la única compuerta.
ARBOL_POR_DEFECTO = ArbolAplicabilidad(
    compuertas=frozenset({"F1"}),
    base=frozenset(CONTROLES_BASE),
    por_filtro={k: frozenset(v) for k, v in CONTROLES_POR_FILTRO.items()},
    origen="semilla",
)


def get_controles_aplicables(
    respuestas: Mapping[str, bool], arbol: ArbolAplicabilidad | None = None
) -> list[str]:
    """
    Recibe un diccionario con las respuestas a las preguntas de filtro:
        {"F1": True, "F2": False, "F3": True, ..., "F7": False}

    Devuelve la lista ordenada de códigos de control que aplican según `arbol` (el de la
    versión vigente de la matriz; sin él, el de la semilla). Si una compuerta es False (o
    falta), devuelve lista vacía.
    """
    return (arbol or ARBOL_POR_DEFECTO).aplicables(respuestas)


def count_controles_aplicables(
    respuestas: Mapping[str, bool], arbol: ArbolAplicabilidad | None = None
) -> int:
    """Atajo para contar sin materializar la lista."""
    return len(get_controles_aplicables(respuestas, arbol))