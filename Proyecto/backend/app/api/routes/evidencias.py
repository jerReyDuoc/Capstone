from fastapi import APIRouter, Depends, File, Request, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alcance import alcance_evidencia, alcance_respuesta
from app.core.cliente import ip_cliente
from app.core.database import get_db
from app.application.use_cases.limites_encuesta import LimiteEncuestaError, LimitesEncuesta
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador
from app.application.use_cases.upload_evidence import UploadEvidenceUseCase
from app.application.schemas.api_schemas import EvidenciaUploadResponse, EvidenciaDetalleResponse
from app.application.use_cases.create_respuesta import RespuestaRechazadaError
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.evidencia_repository import EvidenciaRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.llm.factory import (
    ClaveNoConfiguradaError,
    crear_anonimizador,
    crear_storage_evidencias,
)

router = APIRouter(prefix="/api", tags=["evidencias"])

@router.post(
    "/respuestas/{respuesta_id}/evidencias",
    response_model=EvidenciaUploadResponse,
    status_code=202,
    dependencies=[Depends(alcance_respuesta)],
    responses={429: {"description": "LIMITE_EVIDENCIAS, LIMITE_EVIDENCIAS_IP, CUOTA_LLM_AGOTADA o "
                                    "CUOTA_LLM_GLOBAL_AGOTADA (solo encuesta pública)"}},
)
async def upload_evidencia(
    respuesta_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    # HU-19: límites y cuota diaria de IA de la encuesta pública (antes de guardar nada)
    try:
        reserva = await LimitesEncuesta(db, limitador).reservar_evidencia(respuesta_id, ip_cliente(request))
    except LimiteEncuestaError as e:
        detalle = {"codigo": e.codigo, "mensaje": str(e)}
        headers = {}
        if e.reinicia_en is not None:
            detalle["reinicia_en"] = e.reinicia_en.isoformat().replace("+00:00", "Z")
        if e.reintentar_en_s:
            detalle["reintentar_en_s"] = e.reintentar_en_s
            headers["Retry-After"] = str(e.reintentar_en_s)
        raise HTTPException(status_code=429, detail=detalle, headers=headers)
    except LimitadorNoDisponibleError:
        raise HTTPException(status_code=503, detail={
            "codigo": "LIMITADOR_NO_DISPONIBLE",
            "mensaje": "No podemos recibir evidencias en este momento. Intenta en unos minutos.",
        }, headers={"Retry-After": "60"})

    evidencia_repo = EvidenciaRepository(db)
    respuesta_repo = RespuestaRepository(db)
    try:
        # HU-06: el archivo queda cifrado en reposo hasta que el worker lo anonimiza
        storage = crear_storage_evidencias()
    except ClaveNoConfiguradaError:
        if reserva:
            await reserva.devolver()
        raise HTTPException(status_code=503, detail={
            "codigo": "CIFRADO_NO_CONFIGURADO",
            "mensaje": "El servidor no tiene configurado el cifrado de evidencias (ENTITY_MAP_KEY).",
        })

    use_case = UploadEvidenceUseCase(
        evidencia_repo, respuesta_repo, storage, EvaluacionRepository(db),
        anonimizador=crear_anonimizador(),  # HU-06: nombre de archivo sin PII
    )

    try:
        evidencia = await use_case.execute(respuesta_id, file)
    except RespuestaRechazadaError as e:
        if reserva:
            await reserva.devolver()
        raise HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": str(e)})
    except ValueError as e:
        if reserva:
            await reserva.devolver()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        if reserva:
            await reserva.devolver()
        raise

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
    dependencies=[Depends(alcance_evidencia)],
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