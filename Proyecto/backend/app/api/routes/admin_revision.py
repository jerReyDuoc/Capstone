"""
HU-22 · Bandeja de revisión del Oficial de Cumplimiento (solo admin_therion).

    GET /api/admin/revision/bandeja            listado filtrable (clasificaciones o eventos)
    GET /api/admin/revision/respuestas/{id}    detalle para decidir: control, declaración,
                                               evidencias con lo que dijo el LLM, eventos e historial
    GET /api/admin/revision/resumen            verdad de referencia: LLM vs. revisión humana

Las decisiones usan los endpoints que ya existían (con comentario desde HU-22):
    PATCH /api/respuestas/{id}/revision        {clasificacion_revisada, comentario}
    PATCH /api/seguridad/eventos/{id}/revision {resolucion, comentario}
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.bandeja_revision import (
    ESTADOS_REVISION, MOTIVOS, ORDENES, BandejaRevision, FiltrosBandeja,
)
from app.core.alcance import solo_admin
from app.core.config import settings
from app.core.database import get_db
from app.domain.models.evento_seguridad import OrigenEvento

router = APIRouter(prefix="/api/admin/revision", tags=["revision"], dependencies=[Depends(solo_admin)])

_ORIGENES = [o.value for o in OrigenEvento]


def _invalido(campo: str, valores) -> HTTPException:
    return HTTPException(status_code=422, detail={
        "codigo": "FILTRO_INVALIDO", "campo": campo,
        "mensaje": f"'{campo}' debe ser uno de: {', '.join(valores)}."})


@router.get("/bandeja")
async def bandeja(
    vista: str = Query("clasificaciones", description="clasificaciones | eventos"),
    estado: str = Query("pendiente", description="pendiente | revisada | todas"),
    motivo: str | None = Query(None, description="seguridad | divergencia | sin_resolver | baja_confianza | "
                                                 "resuelta_por_llm | concordante"),
    evaluacion_id: int | None = Query(None, ge=1),
    dominio_id: int | None = Query(None, ge=1),
    criticidad: str | None = Query(None, max_length=20),
    origen: str | None = Query(None, description="Solo eventos: justificacion | evidencia | tutor ..."),
    orden: str = Query("prioridad", description="prioridad | reciente"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    HU-22 C1. Pendientes de revisión con sus filtros y los contadores para las pestañas.

    En `clasificaciones`, por defecto se listan las pendientes con algún motivo prioritario
    (todo menos `concordante`) ordenadas por urgencia: seguridad, divergencia, sin resolver,
    baja confianza y resueltas por el LLM; a igual motivo, la criticidad del control.
    """
    if vista not in ("clasificaciones", "eventos"):
        raise _invalido("vista", ("clasificaciones", "eventos"))
    if estado not in ESTADOS_REVISION:
        raise _invalido("estado", ESTADOS_REVISION)
    if motivo is not None and motivo not in MOTIVOS:
        raise _invalido("motivo", MOTIVOS)
    if origen is not None and origen not in _ORIGENES:
        raise _invalido("origen", _ORIGENES)
    if orden not in ORDENES:
        raise _invalido("orden", ORDENES)
    filtros = FiltrosBandeja(vista=vista, estado=estado, motivo=motivo, evaluacion_id=evaluacion_id,
                             dominio_id=dominio_id, criticidad=criticidad, origen=origen, orden=orden,
                             page=page, size=size)
    return await BandejaRevision(db, settings.UMBRAL_CONFIANZA).bandeja(filtros)


@router.get("/respuestas/{respuesta_id}")
async def detalle_respuesta(respuesta_id: int, db: AsyncSession = Depends(get_db)):
    """HU-22: todo lo que el oficial necesita para confirmar o corregir una clasificación."""
    detalle = await BandejaRevision(db, settings.UMBRAL_CONFIANZA).detalle_respuesta(respuesta_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail={"codigo": "RESPUESTA_NO_ENCONTRADA",
                                                     "mensaje": "Respuesta no encontrada."})
    return detalle


@router.get("/resumen")
async def resumen(db: AsyncSession = Depends(get_db)):
    """
    HU-22: verdad de referencia. Revisiones confirmadas/corregidas, precisión del LLM contra la
    revisión humana (misma métrica que /api/ia/metricas) y aciertos de la detección de ataques.
    """
    return await BandejaRevision(db, settings.UMBRAL_CONFIANZA).resumen()
