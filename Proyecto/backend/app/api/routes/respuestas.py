import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.alcance import actor_opcional, alcance_respuesta, solo_admin, verificar_alcance
from app.core.autenticacion import Actor
from app.core.database import get_db
from app.application.use_cases.create_respuesta import (
    CreateRespuestaUseCase,
    InyeccionDetectadaError,
    RespuestaRechazadaError,
    ResultadoRespuesta,
)
from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.application.schemas.api_schemas import RespuestaDetalleResponse, EvidenciaDetalleResponse
from app.infrastructure.repositories.evaluacion_repository import EvaluacionRepository
from app.infrastructure.repositories.respuesta_repository import RespuestaRepository
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
from app.infrastructure.security.prompt_guard import ReglasPromptGuard
from app.infrastructure.llm.factory import crear_anonimizador
from app.domain.models.respuesta import DecisionRevision, EstadoClasificacion, FuenteClasificacion
from app.domain.models.evaluacion import Evaluacion
from app.application.ai.anonimizador import AnonimizacionError
from app.application.use_cases.generate_resumen import GenerateResumenUseCase
from app.core.cliente import huella
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/respuestas", tags=["respuestas"])

class CreateRespuestaRequest(BaseModel):
    evaluacion_id: int
    matriz_control_id: int
    estado_clasificacion: str
    justificacion: str


class UpdateRespuestaRequest(BaseModel):
    estado_clasificacion: str
    justificacion: str


def _use_case(db: AsyncSession, actor: Actor | None = None) -> CreateRespuestaUseCase:
    guard = ReglasPromptGuard()

    def auditar(respuesta, detalle: dict) -> None:
        # HU-09: la modificación queda en el audit_log en la MISMA transacción que el cambio.
        # Sin token (solo con EXIGIR_TOKEN_EVALUACIONES=false, desarrollo) el actor es anónimo.
        BitacoraRepository(db).registrar(
            accion=Accion.RESPUESTA_MODIFICADA, entidad="respuestas", entidad_id=respuesta.id,
            actor=actor, detalle=detalle,
        )

    return CreateRespuestaUseCase(
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
    payload: CreateRespuestaRequest,
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
    payload: UpdateRespuestaRequest,
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

class RevisionRequest(BaseModel):
    clasificacion_revisada: str
    # HU-22 criterio 2: confirmar o corregir SIEMPRE lleva un comentario del oficial
    comentario: str | None = None


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


def _ultima_clasificacion_llm(respuesta) -> str | None:
    """Clasificación que propuso el LLM en la evidencia procesada más reciente (o None)."""
    con_llm = [e for e in (respuesta.evidencias or []) if e.clasificacion_llm]
    if not con_llm:
        return None
    con_llm.sort(key=lambda e: (e.fecha_procesada or date.min, e.id_evidencia))
    return con_llm[-1].clasificacion_llm


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
    repo = RespuestaRepository(db)
    respuesta = await repo.get(respuesta_id)
    if not respuesta:
        raise HTTPException(status_code=404, detail="Respuesta no encontrada")
    comentario = await anonimizar_comentario(comentario)

    anterior = respuesta.estado_clasificacion_final or respuesta.estado_clasificacion
    decision = (DecisionRevision.CONFIRMADA if payload.clasificacion_revisada == anterior
                else DecisionRevision.CORREGIDA).value
    clasificacion_llm = _ultima_clasificacion_llm(respuesta)

    # HU-09: la revisión cambia la clasificación final: queda en el audit_log (misma transacción).
    # HU-22: con la decisión, lo que había declarado el usuario y propuesto el LLM (la verdad de
    # referencia) y solo la huella HMAC y el largo del comentario: el log nunca guarda texto libre.
    BitacoraRepository(db).registrar(
        accion=Accion.RESPUESTA_REVISADA, entidad="respuestas", entidad_id=respuesta.id, actor=_admin,
        detalle={"evaluacion_id": respuesta.evaluacion_id,
                 "estado_final_anterior": respuesta.estado_clasificacion_final,
                 "fuente_anterior": respuesta.fuente_clasificacion,
                 "estado_final_nuevo": payload.clasificacion_revisada,
                 "decision": decision,
                 "estado_declarado": respuesta.estado_clasificacion,
                 "clasificacion_llm": clasificacion_llm,
                 "revision_previa": respuesta.clasificacion_revisada,
                 "comentario_huella": huella(comentario),
                 "comentario_largo": len(comentario)},
    )
    respuesta.clasificacion_revisada = payload.clasificacion_revisada
    respuesta.fecha_revision = date.today()
    respuesta.estado_clasificacion_final = payload.clasificacion_revisada
    respuesta.fuente_clasificacion = FuenteClasificacion.REVISION.value
    respuesta.comentario_revision = comentario
    respuesta.decision_revision = decision
    respuesta.revisor_admin_id = _admin.id
    # HU-02: la brecha sigue al estado vigente (se asigna en no_cumplido y se quita
    # en cualquier otro), también cuando la revisión corrige una decisión del LLM.
    control = None
    if payload.clasificacion_revisada == EstadoClasificacion.NO_CUMPLIDO.value:
        control = await repo.get_control(respuesta.matriz_controles_id_control)
    respuesta.sincronizar_brecha(control)
    await repo.update(respuesta)

    # HU-22: una corrección sobre una evaluación ya cerrada cambia su puntaje (como HU-17)
    puntajes_recalculados = False
    if decision == DecisionRevision.CORREGIDA.value and respuesta.evaluacion_id:
        evaluacion = await db.get(Evaluacion, respuesta.evaluacion_id)
        if evaluacion is not None and evaluacion.esta_cerrada:
            try:
                await GenerateResumenUseCase(db).execute(respuesta.evaluacion_id)
                puntajes_recalculados = True
            except Exception:  # noqa: BLE001 - la revisión ya quedó; el resumen se puede regenerar
                await db.rollback()
                logger.exception("[HU-22] no se pudo recalcular el resumen de la evaluación %s",
                                 respuesta.evaluacion_id)
    return {
        "id_respuesta": respuesta.id,
        "clasificacion_revisada": respuesta.clasificacion_revisada,
        "estado_clasificacion_final": respuesta.estado_clasificacion_final,
        "fuente_clasificacion": respuesta.fuente_clasificacion,
        "decision": decision,
        "comentario": comentario,
        "fecha_revision": respuesta.fecha_revision.isoformat(),
        "puntajes_recalculados": puntajes_recalculados,
    }
