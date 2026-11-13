"""
HU-39 · Asistente de IA para el mapa de datos, el RAT y los informes (rol cliente, contrato vigente).

  GET    /api/asistente                               estado: entrevista, propuestas, revisión, cuota
  POST   /api/asistente/sesiones                      abre o reanuda la entrevista {area?}
  POST   /api/asistente/sesiones/{id}/area            salta a un área {area}
  POST   /api/asistente/sesiones/{id}/respuestas      responde la pregunta actual {texto?, omitir?}
  POST   /api/asistente/sesiones/{id}/cerrar          cierra la entrevista
  POST   /api/asistente/documentos                    analiza un documento (multipart: file, sesion_id?)
  POST   /api/asistente/propuestas/{id}/aceptar       acepta (tal cual o editada) {payload?, version_mapa?}
  POST   /api/asistente/propuestas/{id}/descartar     descarta {motivo}

Todas exigen usuario definitivo y contrato VIGENTE (empresa_con_servicio, HU-30): 401 sin sesión,
403 para otros roles o sin servicio. Lo de otra empresa responde 404.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.asistente_rat import AsistenteError, AsistenteRat
from app.core.config import settings
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/asistente", tags=["asistente de registro (HU-39)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class ServiciosAsistente:
    """Lo que el caso de uso necesita de la capa de IA. Se reemplaza en las pruebas."""

    def __init__(self, agente, anonimizador, registrar_evento_factory=None):
        self.agente = agente
        self.anonimizador = anonimizador
        self.registrar_evento_factory = registrar_evento_factory


async def obtener_servicios_asistente(
    # Sesión PROPIA para métricas y auditoría de IA: un rollback del negocio no borra la métrica.
    sesion_ia: AsyncSession = Depends(get_db, use_cache=False),
) -> ServiciosAsistente:
    from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
    from app.infrastructure.llm.factory import crear_agente, crear_anonimizador
    from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
    from app.infrastructure.security.prompt_guard import ReglasPromptGuard

    try:
        agente = crear_agente(sesion_ia)
        anonimizador = crear_anonimizador()
    except Exception as e:  # noqa: BLE001 - p. ej. falta ENTITY_MAP_KEY: fail-closed, se sigue sin IA
        logger.error("No se pudo crear la capa de IA del asistente (%s)", type(e).__name__)
        return ServiciosAsistente(None, None)
    return ServiciosAsistente(
        agente, anonimizador,
        lambda db: RegistrarEventoSeguridad(EventoSeguridadRepository(db), ReglasPromptGuard()),
    )


def _http(e: AsistenteError) -> HTTPException:
    headers = {"Retry-After": str(e.extra["reintentar_en_s"])} if e.extra.get("reintentar_en_s") else None
    return HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra},
                         headers=headers)


def _caso(db, cliente, servicios: ServiciosAsistente | None, limitador) -> AsistenteRat:
    s = servicios or ServiciosAsistente(None, None)
    registrar = s.registrar_evento_factory(db) if s.registrar_evento_factory else None
    return AsistenteRat(db, cliente, s.agente, s.anonimizador, limitador, registrar)


async def _ejecutar(corutina, status: int = 200):
    # JSONResponse ignora el status_code del decorador: se pasa aquí (201 al crear)
    try:
        return JSONResponse(await corutina, status_code=status, headers=_SIN_CACHE)
    except AsistenteError as e:
        raise _http(e)
    except LimitadorNoDisponibleError:
        raise HTTPException(status_code=503, detail={
            "codigo": "LIMITADOR_NO_DISPONIBLE",
            "mensaje": "El asistente no está disponible ahora. Puedes completar el mapa y el registro a mano."})


class NuevaSesion(BaseModel):
    area: str | None = Field(default=None, max_length=20)


class CambioArea(BaseModel):
    area: str = Field(max_length=20)


class Respuesta(BaseModel):
    texto: str | None = Field(default=None, max_length=8000)
    omitir: bool = False
    sin_ia: bool = False   # guardar sin ayuda automática (cuando la ayuda falló)


class Aceptacion(BaseModel):
    payload: dict | None = None
    version_mapa: int | None = Field(default=None, ge=0)


class Descarte(BaseModel):
    motivo: str | None = Field(default=None, max_length=20)


@router.get("")
async def estado(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db),
                 limitador: Limitador = Depends(obtener_limitador)):
    return await _ejecutar(_caso(db, cliente, None, limitador).estado())


@router.post("/sesiones", status_code=201)
async def iniciar(payload: NuevaSesion, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador)):
    return await _ejecutar(_caso(db, cliente, None, limitador).iniciar(payload.area), status=201)


@router.post("/sesiones/{sesion_id}/area")
async def cambiar_area(sesion_id: int, payload: CambioArea, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                       db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador)):
    return await _ejecutar(_caso(db, cliente, None, limitador).cambiar_area(sesion_id, payload.area))


@router.post("/sesiones/{sesion_id}/respuestas")
async def responder(sesion_id: int, payload: Respuesta, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                    db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador),
                    servicios: ServiciosAsistente = Depends(obtener_servicios_asistente)):
    """C1: la respuesta se analiza (con IA si está disponible) y devuelve las propuestas para revisar."""
    return await _ejecutar(_caso(db, cliente, servicios, limitador).responder(sesion_id, payload.texto,
                                                                               payload.omitir, payload.sin_ia))


@router.post("/sesiones/{sesion_id}/cerrar")
async def cerrar(sesion_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador)):
    return await _ejecutar(_caso(db, cliente, None, limitador).cerrar(sesion_id))


@router.post("/documentos", status_code=201)
async def documento(file: UploadFile = File(...), sesion_id: int | None = Form(None),
                    cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db),
                    limitador: Limitador = Depends(obtener_limitador),
                    servicios: ServiciosAsistente = Depends(obtener_servicios_asistente)):
    """C3: políticas, contratos con proveedores o avisos. El archivo no se guarda (solo su huella)."""
    # Se lee como mucho el máximo + 1 byte: un archivo más grande no llega entero a memoria
    contenido = await file.read(settings.ASISTENTE_DOCUMENTO_MAX_MB * 1024 * 1024 + 1)
    return await _ejecutar(_caso(db, cliente, servicios, limitador).analizar_documento(
        file.filename, contenido, sesion_id), status=201)


@router.post("/propuestas/{propuesta_id}/aceptar")
async def aceptar(propuesta_id: int, payload: Aceptacion, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador)):
    """C4: solo aquí algo propuesto por la IA entra al mapa o al RAT (con las validaciones de siempre)."""
    return await _ejecutar(_caso(db, cliente, None, limitador).aceptar(propuesta_id, payload.payload,
                                                                             payload.version_mapa))


@router.post("/propuestas/{propuesta_id}/descartar")
async def descartar(propuesta_id: int, payload: Descarte, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                    db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador)):
    return await _ejecutar(_caso(db, cliente, None, limitador).descartar(propuesta_id, payload.motivo))
