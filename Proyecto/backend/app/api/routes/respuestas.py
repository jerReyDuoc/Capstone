import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencias.alcance import actor_opcional, alcance_respuesta, solo_admin, verificar_alcance
from app.domain.auth.actor import Actor
from app.core.database import get_db
from app.application.evaluacion.casos_uso.crear_respuesta import (
    CrearRespuestaUseCase,
    InyeccionDetectadaError,
    RespuestaRechazadaError,
    ResultadoRespuesta,
)
from app.application.auditoria.casos_uso.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.api.schemas.comunes import RespuestaDetalleResponse, EvidenciaDetalleResponse
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
from app.infrastructure.security.prompt_injection.guardia_prompt import ReglasGuardiaPrompt
from app.api.dependencias.contenedor import crear_anonimizador
from app.domain.models.respuesta import EstadoClasificacion
from app.application.ai.anonimizador import AnonimizacionError
from app.application.fabricas import fabricas
from app.application.evaluacion.casos_uso.revisar_respuesta import RevisarRespuestaUseCase, RespuestaNoEncontradaError
from app.domain.auditoria.acciones import Accion
from app.api.schemas.respuestas_esquemas import CrearRespuestaRequest, ActualizarRespuestaRequest, RevisionRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/respuestas", tags=["respuestas"])


def _use_case(db: AsyncSession, actor: Actor | None = None) -> CrearRespuestaUseCase:
    guard = ReglasGuardiaPrompt()

    def auditar(respuesta, detalle: dict) -> None:
        # HU-09: la modificación queda en el audit_log en la MISMA transacción que el cambio.
        # Sin token (solo con EXIGIR_TOKEN_EVALUACIONES=false, desarrollo) el actor es anónimo.
        fabricas().bitacora(db).registrar(
            accion=Accion.RESPUESTA_MODIFICADA, entidad="respuestas", entidad_id=respuesta.id,
            actor=actor, detalle=detalle,
        )

    return CrearRespuestaUseCase(
        RespuestaRepository(db),
        EvaluacionRepository(db),
        guard=guard,
        registrar_evento=RegistrarEventoSeguridad(EventoSeguridadRepository(db), guard),
        anonimizador=crear_anonimizador(),  # HU-06: la justificación se guarda anonimizada
        auditar_modificacion=auditar,
    )


async def _ejecutar(operacion) -> ResultadoRespuesta:
    """Traduce los errores del caso de uso a HTTP con un cuerpo {codigo, mensaje}."""
    try:
        return await operacion
    except InyeccionDetectadaError as e:
        raise HTTPException(status_code=422, detail={"codigo": "PROMPT_INJECTION", "mensaje": str(e)})
    except RespuestaRechazadaError as e:
        raise HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _cuerpo(resultado: ResultadoRespuesta) -> dict:
    return {
        "id_respuesta": resultado.respuesta.id,
        "creada": resultado.creada,
        "actualizada": not resultado.creada and resultado.modificada,
    }


@router.post(
    "/",
    status_code=201,
    responses={
        200: {"description": "Ya existía una respuesta para ese control: se actualizó (o no cambió)"},
        404: {"description": "Evaluación o control inexistente"},
        409: {"description": "Evaluación cerrada o filtro F1–F7 sin completar"},
        422: {"description": "Control no aplicable según el filtro, o posible prompt injection"},
    },
)
async def create_respuesta(
    payload: CrearRespuestaRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    actor: Actor | None = Depends(actor_opcional),
):
    """
    Guarda la respuesta a un control (HU-01, guardado automático del progreso).

    Es un **upsert** por (evaluación, control): la primera vez crea la fila (201);
    si el control ya estaba respondido la actualiza (200, mismo `id_respuesta`).
    """
    await verificar_alcance(db, actor, payload.evaluacion_id)  # HU-19: solo su evaluación
    resultado = await _ejecutar(_use_case(db, actor).guardar(
        evaluacion_id=payload.evaluacion_id,
        matriz_control_id=payload.matriz_control_id,
        estado_clasificacion=payload.estado_clasificacion,
        justificacion=payload.justificacion,
    ))
    if not resultado.creada:
        response.status_code = 200
    return _cuerpo(resultado)


@router.put("/{respuesta_id}")
async def update_respuesta(
    respuesta_id: int,
    payload: ActualizarRespuestaRequest,
    db: AsyncSession = Depends(get_db),
    actor: Actor | None = Depends(alcance_respuesta),
):
    """Modifica la declaración de una respuesta existente (mismas validaciones que el POST)."""
    resultado = await _ejecutar(_use_case(db, actor).actualizar(
        respuesta_id=respuesta_id,
        estado_clasificacion=payload.estado_clasificacion,
        justificacion=payload.justificacion,
    ))
    return _cuerpo(resultado)

@router.get("/{respuesta_id}", response_model=RespuestaDetalleResponse, dependencies=[Depends(alcance_respuesta)])
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


# HU-22: largo del comentario de revisión (se valida a mano para responder {codigo, mensaje})
COMENTARIO_MIN = 10
COMENTARIO_MAX = 1000


def validar_comentario(comentario: str | None) -> str:
    texto = " ".join((comentario or "").split())
    if len(texto) < COMENTARIO_MIN:
        raise HTTPException(status_code=422, detail={
            "codigo": "COMENTARIO_REQUERIDO", "campo": "comentario",
            "mensaje": f"Explica la decisión en al menos {COMENTARIO_MIN} caracteres."})
    if len(texto) > COMENTARIO_MAX:
        raise HTTPException(status_code=422, detail={
            "codigo": "COMENTARIO_DEMASIADO_LARGO", "campo": "comentario",
            "mensaje": f"El comentario admite hasta {COMENTARIO_MAX} caracteres."})
    return texto


async def anonimizar_comentario(texto: str) -> str:
    """HU-06: el comentario se guarda sin PII (fail-closed: si el motor NER falla, no se guarda)."""
    try:
        return await crear_anonimizador().anonimizar(texto)
    except AnonimizacionError:
        raise HTTPException(status_code=503, detail={
            "codigo": "ANONIMIZACION_NO_DISPONIBLE",
            "mensaje": "No se pudo anonimizar el comentario; por seguridad no se guardó la revisión. "
                       "Intenta nuevamente en unos minutos."})


@router.patch("/{respuesta_id}/revision")
async def revisar_respuesta(
    respuesta_id: int,
    payload: RevisionRequest,
    db: AsyncSession = Depends(get_db),
    _admin: Actor = Depends(solo_admin),
):
    """
    Revisión humana del Oficial de Cumplimiento. Fija la clasificación final y
    sirve como verdad de referencia para medir la precisión del LLM (/api/ia/metricas).

    HU-20: solo administradores de Therion Labs (401 sin token, 403 para el encuestado
    o el referente, que nunca revisan su propio diagnóstico).

    HU-22: exige un `comentario` (10 a 1000 caracteres, se guarda anonimizado). La revisión
    es **confirmada** si deja la clasificación vigente igual y **corregida** si la cambia;
    puede repetirse (cada una queda en el audit_log). Si la evaluación ya está cerrada, se
    recalculan sus puntajes con la clasificación revisada.
    """
    valores = EstadoClasificacion.resolutivos()
    if payload.clasificacion_revisada not in valores:
        raise HTTPException(
            status_code=400,
            detail=f"Clasificación inválida. Debe ser una de: {', '.join(valores)}",
        )
    comentario = validar_comentario(payload.comentario)
    try:
        r = await RevisarRespuestaUseCase(db, RespuestaRepository(db)).revisar(
            respuesta_id, payload.clasificacion_revisada, comentario, _admin, anonimizar_comentario)
    except RespuestaNoEncontradaError:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    respuesta = r.respuesta
    return {
        "id_respuesta": respuesta.id,
        "clasificacion_revisada": respuesta.clasificacion_revisada,
        "estado_clasificacion_final": respuesta.estado_clasificacion_final,
        "fuente_clasificacion": respuesta.fuente_clasificacion,
        "decision": r.decision,
        "comentario": r.comentario,
        "fecha_revision": respuesta.fecha_revision.isoformat(),
        "puntajes_recalculados": r.puntajes_recalculados,
    }
