from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.application.use_cases.create_respuesta import CreateRespuestaUseCase, InyeccionDetectadaError
from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.application.schemas.api_schemas import RespuestaDetalleResponse, EvidenciaDetalleResponse
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
from app.infrastructure.security.prompt_guard import ReglasPromptGuard
from app.domain.models.respuesta import EstadoClasificacion, FuenteClasificacion

router = APIRouter(prefix="/api/respuestas", tags=["respuestas"])

class CreateRespuestaRequest(BaseModel):
    evaluacion_id: int
    matriz_control_id: int
    estado_clasificacion: str
    justificacion: str

@router.post("/", status_code=201)
async def create_respuesta(
    payload: CreateRespuestaRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = RespuestaRepository(db)
    guard = ReglasPromptGuard()
    use_case = CreateRespuestaUseCase(
        repo,
        guard=guard,
        registrar_evento=RegistrarEventoSeguridad(EventoSeguridadRepository(db), guard),
    )
    try:
        respuesta = await use_case.execute(
            evaluacion_id=payload.evaluacion_id,
            matriz_control_id=payload.matriz_control_id,
            estado_clasificacion=payload.estado_clasificacion,
            justificacion=payload.justificacion,
        )
    except InyeccionDetectadaError as e:
        raise HTTPException(
            status_code=422,
            detail={"codigo": "PROMPT_INJECTION", "mensaje": str(e)},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id_respuesta": respuesta.id}

@router.get("/{respuesta_id}", response_model=RespuestaDetalleResponse)
async def get_respuesta(respuesta_id: int, db: AsyncSession = Depends(get_db)):
    repo = RespuestaRepository(db)
    respuesta = await repo.get(respuesta_id)
    if not respuesta:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")

    evidencias = [
        EvidenciaDetalleResponse(
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
        for e in respuesta.evidencias
    ]

    return RespuestaDetalleResponse(
        id_respuesta=respuesta.id,
        estado_clasificacion=respuesta.estado_clasificacion,
        justificacion_usuario=respuesta.justificacion_usuario,
        estado_clasificacion_final=respuesta.estado_clasificacion_final,
        fuente_clasificacion=respuesta.fuente_clasificacion,
        confianza_clasificacion=respuesta.confianza_clasificacion,
        fecha_validacion=respuesta.fecha_validacion,
        evidencias=evidencias,
    )

class RevisionRequest(BaseModel):
    clasificacion_revisada: str


@router.patch("/{respuesta_id}/revision")
async def revisar_respuesta(
    respuesta_id: int,
    payload: RevisionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Revisión humana del Oficial de Cumplimiento. Fija la clasificación final y
    sirve como verdad de referencia para medir la precisión del LLM (/api/ia/metricas).
    """
    valores = EstadoClasificacion.declarables()
    if payload.clasificacion_revisada not in valores:
        raise HTTPException(
            status_code=400,
            detail=f"Clasificación inválida. Debe ser una de: {', '.join(valores)}",
        )
    repo = RespuestaRepository(db)
    respuesta = await repo.get(respuesta_id)
    if not respuesta:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")

    respuesta.clasificacion_revisada = payload.clasificacion_revisada
    respuesta.fecha_revision = date.today()
    respuesta.estado_clasificacion_final = payload.clasificacion_revisada
    respuesta.fuente_clasificacion = FuenteClasificacion.REVISION.value
    if payload.clasificacion_revisada == EstadoClasificacion.NO_CUMPLIDO.value:
        control = await repo.get_control(respuesta.matriz_controles_id_control)
        if control and control.catalogo_brechas_id_brecha:
            respuesta.catalogo_brechas_id_brecha = control.catalogo_brechas_id_brecha
    await repo.update(respuesta)
    return {
        "id_respuesta": respuesta.id,
        "clasificacion_revisada": respuesta.clasificacion_revisada,
        "estado_clasificacion_final": respuesta.estado_clasificacion_final,
        "fuente_clasificacion": respuesta.fuente_clasificacion,
    }
