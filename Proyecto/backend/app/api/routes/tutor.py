"""
HU-15 · Agente IA Tutor del panel de formación (rol cliente, contrato vigente).

  GET    /api/tutor/contexto?ruta_id=                     brechas que verá el tutor, nivel sugerido y cuota
  GET    /api/tutor/conversaciones                        conversaciones de la empresa
  POST   /api/tutor/conversaciones                        abre una conversación {ruta_id?, nivel?}
  GET    /api/tutor/conversaciones/{id}                   conversación con sus mensajes
  PATCH  /api/tutor/conversaciones/{id}                   cambia el nivel {nivel}
  DELETE /api/tutor/conversaciones/{id}                   la borra con sus mensajes
  POST   /api/tutor/conversaciones/{id}/mensajes          envía un mensaje y devuelve la respuesta del tutor

Todas exigen usuario definitivo y contrato VIGENTE (empresa_con_servicio, HU-30): 401 sin
sesión, 403 NO_AUTORIZADO para otros roles (usuario temporal, admin) y 403
CONTRATO_NO_VIGENTE sin servicio. Una conversación de otra empresa responde 404.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.tutor_ia import TutorError, TutorIA
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tutor", tags=["agente IA tutor (HU-15)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class ServiciosTutor:
    """Lo que el caso de uso necesita de la capa de IA. Se reemplaza en las pruebas."""

    def __init__(self, agente, anonimizador, registrar_evento_factory=None):
        self.agente = agente
        self.anonimizador = anonimizador
        self.registrar_evento_factory = registrar_evento_factory


async def obtener_servicios_tutor(
    # Sesión PROPIA para métricas y auditoría de IA (use_cache=False => otra sesión): un
    # rollback del negocio no borra la métrica, igual que en el worker.
    sesion_ia: AsyncSession = Depends(get_db, use_cache=False),
) -> ServiciosTutor:
    from app.infrastructure.llm.factory import crear_agente, crear_anonimizador
    from app.infrastructure.security.prompt_guard import ReglasPromptGuard
    from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
    from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository

    try:
        agente = crear_agente(sesion_ia)
        anonimizador = crear_anonimizador()
    except Exception as e:  # noqa: BLE001 - p. ej. falta ENTITY_MAP_KEY: fail-closed
        logger.error("No se pudo crear la capa de IA del tutor (%s)", type(e).__name__)
        return ServiciosTutor(None, None)
    return ServiciosTutor(
        agente, anonimizador,
        lambda db: RegistrarEventoSeguridad(EventoSeguridadRepository(db), ReglasPromptGuard()),
    )


def _http(e: TutorError) -> HTTPException:
    headers = {"Retry-After": str(e.extra["reintentar_en_s"])} if e.extra.get("reintentar_en_s") else None
    return HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra},
                         headers=headers)


def _sin_limitador() -> HTTPException:
    return HTTPException(status_code=503, detail={
        "codigo": "LIMITADOR_NO_DISPONIBLE", "mensaje": "El tutor no está disponible ahora. Intenta en unos minutos."})


def _tutor(db, cliente, servicios: ServiciosTutor | None, limitador) -> TutorIA:
    s = servicios or ServiciosTutor(None, None)
    registrar = s.registrar_evento_factory(db) if s.registrar_evento_factory else None
    return TutorIA(db, cliente, s.agente, s.anonimizador, limitador, registrar)


@router.get("/contexto")
async def contexto(
    ruta_id: int | None = Query(None, ge=1),
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    """C1: lo que verá el tutor (solo las brechas de la evaluación vigente de tu empresa)."""
    try:
        return JSONResponse(await _tutor(db, cliente, None, limitador).contexto(ruta_id), headers=_SIN_CACHE)
    except TutorError as e:
        raise _http(e)
    except LimitadorNoDisponibleError:
        raise _sin_limitador()


@router.get("/conversaciones")
async def listar(
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
):
    return JSONResponse(await _tutor(db, cliente, None, None).listar(), headers=_SIN_CACHE)


class NuevaConversacion(BaseModel):
    ruta_id: int | None = Field(None, ge=1, description="Módulo formativo desde el que se abre (fija el nivel por defecto)")
    nivel: str | None = Field(None, max_length=20, description="Inicial | Intermedio | Avanzado (vacío = el de la ruta)")


@router.post("/conversaciones", status_code=201)
async def crear(
    payload: NuevaConversacion | None = None,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    p = payload or NuevaConversacion()
    try:
        return await _tutor(db, cliente, None, limitador).crear(p.ruta_id, p.nivel)
    except TutorError as e:
        raise _http(e)
    except LimitadorNoDisponibleError:
        raise _sin_limitador()


@router.get("/conversaciones/{conversacion_id}")
async def obtener(
    conversacion_id: int,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    try:
        return JSONResponse(await _tutor(db, cliente, None, limitador).obtener(conversacion_id), headers=_SIN_CACHE)
    except TutorError as e:
        raise _http(e)
    except LimitadorNoDisponibleError:
        raise _sin_limitador()


class CambioNivel(BaseModel):
    nivel: str = Field(..., max_length=20)


@router.patch("/conversaciones/{conversacion_id}")
async def cambiar_nivel(
    conversacion_id: int,
    payload: CambioNivel,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
):
    """C2: el usuario cambia el nivel (Inicial, Intermedio, Avanzado) de la conversación."""
    try:
        return await _tutor(db, cliente, None, None).cambiar_nivel(conversacion_id, payload.nivel)
    except TutorError as e:
        raise _http(e)


@router.delete("/conversaciones/{conversacion_id}", status_code=204, response_class=Response)
async def eliminar(
    conversacion_id: int,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
):
    try:
        await _tutor(db, cliente, None, None).eliminar(conversacion_id)
    except TutorError as e:
        raise _http(e)
    return Response(status_code=204)


class NuevoMensaje(BaseModel):
    # El largo real lo controla TUTOR_MAX_CHARS_MENSAJE en el caso de uso; esto es un tope duro.
    texto: str = Field(..., max_length=20000)


@router.post("/conversaciones/{conversacion_id}/mensajes")
async def enviar(
    conversacion_id: int,
    payload: NuevoMensaje,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
    servicios: ServiciosTutor = Depends(obtener_servicios_tutor),
):
    """C3: asistencia conversacional. Respuesta síncrona, ya validada y anclada a tus brechas."""
    try:
        return JSONResponse(
            await _tutor(db, cliente, servicios, limitador).enviar(conversacion_id, payload.texto),
            headers=_SIN_CACHE,
        )
    except TutorError as e:
        raise _http(e)
    except LimitadorNoDisponibleError:
        raise _sin_limitador()
