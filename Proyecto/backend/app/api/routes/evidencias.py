from fastapi import APIRouter, Depends, File, Request, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.application.use_cases.upload_evidence import UploadEvidenceUseCase
from app.application.schemas.api_schemas import EvidenciaUploadResponse, EvidenciaDetalleResponse
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.storage.local_storage import LocalFileStorage

router = APIRouter(prefix="/api", tags=["evidencias"])

@router.post(
    "/respuestas/{respuesta_id}/evidencias",
    response_model=EvidenciaUploadResponse,
    status_code=202,
)
async def upload_evidencia(
    respuesta_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    evidencia_repo = EvidenciaRepository(db)
    respuesta_repo = RespuestaRepository(db)
    storage = LocalFileStorage()

    use_case = UploadEvidenceUseCase(evidencia_repo, respuesta_repo, storage)

    try:
        evidencia = await use_case.execute(respuesta_id, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Encolar tarea en ARQ
    await request.app.state.arq.enqueue_job("process_evidence_task", evidencia.id_evidencia)

    return EvidenciaUploadResponse(
        id_evidencia=evidencia.id_evidencia,
        nombre_archivo=evidencia.nombre_archivo,
        estado_validacion=evidencia.estado_validacion,
        mensaje="Evidencia recibida. Procesando validación con IA.",
    )

@router.get(
    "/evidencias/{evidencia_id}",
    response_model=EvidenciaDetalleResponse,
)
async def get_evidencia(evidencia_id: int, db: AsyncSession = Depends(get_db)):
    repo = EvidenciaRepository(db)
    e = await repo.get(evidencia_id)
    if not e:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada")
    return EvidenciaDetalleResponse(
        id_evidencia=e.id_evidencia,
        nombre_archivo=e.nombre_archivo,
        estado_validacion=e.estado_validacion,
        clasificacion_llm=e.clasificacion_llm,
        confianza=e.confianza,
        justificacion_llm=e.justificacion_llm,
        datos_extraidos=e.datos_extraidos,
        errores_validacion=e.errores_validacion,
        fecha_subida=e.fecha_subida,
        fecha_procesada=e.fecha_procesada,
    )