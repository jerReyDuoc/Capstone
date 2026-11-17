"""Constantes, errores y helpers compartidos del registro de actividades."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.domain.mapa_datos.modelo_mapa import Elemento, Flujo
from app.domain.models.mapa_datos_tablas import MapaElemento, MapaFlujo
from app.domain.rat import analisis_rat as analisis

logger = logging.getLogger("app.application.rat.casos_uso.registro_actividades_casos")

MAX_ACTIVIDADES = 300
MAX_MOTIVOS = 20


class RatError(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, **extra):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.extra = status, codigo, mensaje, extra


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _elemento(r: MapaElemento) -> Elemento:
    from app.application.mapa_datos.casos_uso import elemento_de_fila
    return elemento_de_fila(r)


def _flujo(r: MapaFlujo) -> Flujo:
    from app.application.mapa_datos.casos_uso import flujo_de_fila
    return flujo_de_fila(r)


def _evaluar(contenido: dict, elementos: list[Elemento], flujos: list[Flujo]) -> tuple[dict, dict]:
    deriv = analisis.derivados(contenido, elementos, flujos)
    return deriv, analisis.completitud(contenido, deriv)
