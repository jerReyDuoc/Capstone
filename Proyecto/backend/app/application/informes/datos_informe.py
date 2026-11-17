"""
Datos del PDF del informe de evaluación (HU-11, HU-12, HU-21): DTO puro y nombre del archivo.
El dibujo del PDF vive en app/infrastructure/documentos/pdf/informe_evaluacion_pdf.py (A-14).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.evaluacion.analisis_brechas import Brecha, ComparativaDominio, FiltrosBrechas, PlanFormativo
from app.application.informes.ficha import FichaInforme


@dataclass(frozen=True)
class DatosInforme:
    evaluacion_id: int
    rubro: str | None
    puntaje_general: float
    controles_evaluados: int
    en_revision: int
    comparativa: list[ComparativaDominio]
    brechas_total: int
    brechas: list[Brecha]              # ya filtradas
    filtros: FiltrosBrechas
    plan: PlanFormativo
    generado: datetime
    # HU-21: ficha de identificación (None solo en pruebas antiguas que arman el PDF a mano:
    # el PDF sale igual, con el aviso legal y los puntajes de la comparativa)
    ficha: FichaInforme | None = None
    # Todas las brechas, sin filtrar (la huella y el resumen de la portada no dependen del filtro)
    brechas_completas: tuple[Brecha, ...] = ()


def nombre_archivo(evaluacion_id: int, fecha: datetime) -> str:
    return f"informe_evaluacion-{evaluacion_id}_{fecha:%Y-%m-%d}.pdf"
