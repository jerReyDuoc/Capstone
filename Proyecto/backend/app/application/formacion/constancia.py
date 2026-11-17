"""
HU-26 criterio 3: datos de la constancia de un módulo formativo completado (puro).
El PDF se dibuja en app/infrastructure/documentos/pdf/constancia.py (A-14).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class DatosConstancia:
    razon_social: str
    rut: str
    participante: str
    modulo: str
    dominio: str | None
    nivel: str | None
    horas: int | None
    modalidad: str | None
    objetivo: str | None
    fecha_completado: datetime
    puntaje: float | None
    codigo: str


def nombre_constancia(d: DatosConstancia) -> str:
    return f"constancia_{d.codigo}.pdf"


def _fecha_chile(f: datetime) -> datetime:
    if f.tzinfo is None:
        f = f.replace(tzinfo=timezone.utc)
    return f.astimezone(ZoneInfo("America/Santiago"))


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")


def fecha_larga(f: datetime) -> str:
    f = _fecha_chile(f)
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"
