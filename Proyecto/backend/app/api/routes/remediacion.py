"""
HU-17 · Remediación: re-evaluar un control con evidencia nueva (rol cliente).

  GET  /api/remediacion/evaluaciones/{evaluacion_id}            controles con brecha, su formación
                                                                (HU-26) y su última evidencia
  POST /api/remediacion/respuestas/{respuesta_id}/evidencias    multipart: file + estado_declarado
                                                                (+ justificacion opcional) → 202
  GET  /api/remediacion/evidencias/{evidencia_id}               resultado del análisis y el puntaje
                                                                recalculado (el panel lo consulta
                                                                hasta que termina)

Todas exigen el servicio pagado activo (app/core/servicio_pagado.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
from app.application.use_cases.remediacion import Remediacion, RemediacionError, evidencia_dict
from app.core.config import settings
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador
from app.infrastructure.llm.factory import ClaveNoConfiguradaError, crear_anonimizador, crear_storage_evidencias
from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
from app.infrastructure.security.prompt_guard import ReglasPromptGuard

router = APIRouter(prefix="/api/remediacion", tags=["remediación con evidencia (HU-17)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _http(e: RemediacionError) -> HTTPException:
    headers = {"Retry-After": str(e.extra["reintentar_en_s"])} if e.extra.get("reintentar_en_s") else None
    return HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra},
                         headers=headers)


@router.get("/evaluaciones/{evaluacion_id}")
async def listar(evaluacion_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db)):
    try:
        return JSONResponse(await Remediacion(db, cliente).listar(evaluacion_id), headers=_SIN_CACHE)
    except RemediacionError as e:
        raise _http(e)


@router.post("/respuestas/{respuesta_id}/evidencias", status_code=202)
async def subir(
    respuesta_id: int,
    request: Request,
    file: UploadFile = File(...),
    estado_declarado: str = Form(...),
    justificacion: str | None = Form(None),
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    # Se lee como mucho el máximo + 1 byte: un archivo más grande no llega entero a memoria
    contenido = await file.read(settings.EVIDENCIA_MAX_MB * 1024 * 1024 + 1)
    try:
        storage = crear_storage_evidencias()  # HU-06: cifrado en reposo hasta que el worker lo anonimiza
    except ClaveNoConfiguradaError:
        raise HTTPException(status_code=503, detail={
            "codigo": "CIFRADO_NO_CONFIGURADO",
            "mensaje": "El servidor no tiene configurado el cifrado de evidencias (ENTITY_MAP_KEY).",
        })
    guard = ReglasPromptGuard()
    try:
        evidencia = await Remediacion(db, cliente).subir(
            respuesta_id, file.filename, contenido, estado_declarado, justificacion,
            storage=storage, anonimizador=crear_anonimizador(), guard=guard,
            registrar_evento=RegistrarEventoSeguridad(EventoSeguridadRepository(db), guard),
            limitador=limitador,
        )
    except RemediacionError as e:
        raise _http(e)
    except LimitadorNoDisponibleError:
        raise HTTPException(status_code=503, detail={
            "codigo": "LIMITADOR_NO_DISPONIBLE", "mensaje": "No podemos recibir evidencias ahora. Intenta en unos minutos."})
    await request.app.state.arq.enqueue_job("process_evidence_task", evidencia.id_evidencia)
    return {**evidencia_dict(evidencia), "mensaje": "Recibimos la evidencia. La estamos analizando."}


@router.get("/evidencias/{evidencia_id}")
async def detalle(evidencia_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db)):
    try:
        return JSONResponse(await Remediacion(db, cliente).detalle(evidencia_id), headers=_SIN_CACHE)
    except RemediacionError as e:
        raise _http(e)
