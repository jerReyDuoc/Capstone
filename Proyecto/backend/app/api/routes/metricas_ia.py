from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.obtener_metricas_ia import ObtenerMetricasIAUseCase
from app.core.alcance import solo_admin
from app.core.config import settings
from app.core.database import get_db

# HU-20: las métricas de la capa de IA son solo para administradores de Therion Labs
router = APIRouter(prefix="/api/ia", tags=["ia"], dependencies=[Depends(solo_admin)])


@router.get("/metricas")
async def metricas_ia(
    desde: datetime | None = Query(None, description="ISO 8601, UTC"),
    hasta: datetime | None = Query(None, description="ISO 8601, UTC"),
    tarea: str | None = Query(None, examples=["validar_evidencia"]),
    modelo: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Métricas de la capa de Políticas e IA:
    - operacion_modelo: tasa de error (global y por tipo), latencia, tokens y costo.
    - precision_modelo: LLM vs. revisión humana (accuracy, P/R/F1, matriz de confusión).
    - sanitizacion: entidades anonimizadas por tipo y fallos del motor NER.
    """
    return await ObtenerMetricasIAUseCase(db, settings.UMBRAL_CONFIANZA).execute(
        desde=desde, hasta=hasta, tarea=tarea, modelo=modelo
    )
