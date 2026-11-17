"""Rutas calculadas de la suite de pruebas (independientes de la subcarpeta del test)."""
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]  # backend/tests/
DATOS = TESTS / "data"  # backend/tests/data/
RAIZ = TESTS.parent  # backend/
