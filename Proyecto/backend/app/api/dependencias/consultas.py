"""Fábricas `Depends` de los casos de uso de consulta (A-41)."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.evaluacion.casos_uso.consultar_evaluaciones import ConsultarEvaluacionesUseCase
from app.application.evaluacion.casos_uso.reportes_evaluacion import ReportesEvaluacionUseCase
from app.core.database import get_db
from app.infrastructure.repositories.bitacora_repository import BitacoraRepository
from app.infrastructure.repositories.consulta_evaluaciones_repository import ConsultaEvaluacionesRepository
from app.infrastructure.repositories.reportes_repository import ReportesRepository


def consultar_evaluaciones_uc(db: AsyncSession = Depends(get_db)) -> ConsultarEvaluacionesUseCase:
    return ConsultarEvaluacionesUseCase(ConsultaEvaluacionesRepository(db), db, BitacoraRepository(db))


def reportes_evaluacion_uc(db: AsyncSession = Depends(get_db)) -> ReportesEvaluacionUseCase:
    return ReportesEvaluacionUseCase(ReportesRepository(db))
