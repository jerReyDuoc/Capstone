"""
HU-26 · Recorrido de los módulos formativos y avance de la empresa (rol cliente).

  GET  /api/formacion/avance?evaluacion_id=                         panel de formación: avance por
                                                                    módulo, dimensión y nivel, y brechas
                                                                    con la formación hecha
  GET  /api/formacion/modulos/{ruta_id}?evaluacion_id=              lecciones, material y actividad
                                                                    (sin las respuestas correctas)
  POST /api/formacion/modulos/{ruta_id}/lecciones/{orden}/vista     marca la lección como vista
  POST /api/formacion/modulos/{ruta_id}/verificacion                corrige la actividad final
  GET  /api/formacion/modulos/{ruta_id}/constancia                  constancia PDF (solo completado)

Todas exigen el servicio pagado activo (app/core/servicio_pagado.py, punto único para HU-30).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.formacion.constancia_pdf import PdfNoDisponibleError
from app.application.use_cases.formacion_empresa import FormacionEmpresa, FormacionError
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador

router = APIRouter(prefix="/api/formacion", tags=["formación de la empresa (HU-26)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _http(e: FormacionError) -> HTTPException:
    headers = {"Retry-After": str(e.extra["reintentar_en_s"])} if e.extra.get("reintentar_en_s") else None
    return HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra},
                         headers=headers)


def _sin_limitador() -> HTTPException:
    return HTTPException(status_code=503, detail={
        "codigo": "LIMITADOR_NO_DISPONIBLE", "mensaje": "No podemos registrar la actividad ahora. Intenta en unos minutos."})


@router.get("/avance")
async def avance(
    evaluacion_id: int | None = Query(None, ge=1),
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
):
    """Criterio 2: módulos iniciados y completados y % por dimensión y nivel."""
    try:
        return JSONResponse(await FormacionEmpresa(db, cliente).avance(evaluacion_id), headers=_SIN_CACHE)
    except FormacionError as e:
        raise _http(e)


@router.get("/modulos/{ruta_id}")
async def modulo(
    ruta_id: int,
    evaluacion_id: int | None = Query(None, ge=1),
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    """Criterio 1: el módulo para recorrerlo (contenido, material de apoyo y actividad)."""
    try:
        return JSONResponse(await FormacionEmpresa(db, cliente).modulo(ruta_id, evaluacion_id, limitador),
                            headers=_SIN_CACHE)
    except FormacionError as e:
        raise _http(e)


class VistaRequest(BaseModel):
    evaluacion_id: int | None = Field(None, ge=1)


@router.post("/modulos/{ruta_id}/lecciones/{orden}/vista")
async def marcar_vista(
    ruta_id: int,
    orden: int,
    payload: VistaRequest | None = None,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await FormacionEmpresa(db, cliente).marcar_leccion(
            ruta_id, orden, payload.evaluacion_id if payload else None)
    except FormacionError as e:
        raise _http(e)


class VerificacionRequest(BaseModel):
    # {pregunta_id: id de la opción elegida}
    respuestas: dict[int, int] = Field(default_factory=dict, max_length=50)
    evaluacion_id: int | None = Field(None, ge=1)


@router.post("/modulos/{ruta_id}/verificacion")
async def verificar(
    ruta_id: int,
    payload: VerificacionRequest,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    """Corrige la actividad en el servidor. Aprobada: módulo completado con fecha y constancia."""
    try:
        return await FormacionEmpresa(db, cliente).verificar(ruta_id, payload.respuestas, payload.evaluacion_id,
                                                             limitador)
    except FormacionError as e:
        raise _http(e)
    except LimitadorNoDisponibleError:
        raise _sin_limitador()


@router.get("/modulos/{ruta_id}/constancia", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
async def constancia(
    ruta_id: int,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
):
    """Criterio 3: constancia PDF del módulo completado."""
    try:
        pdf, nombre = await FormacionEmpresa(db, cliente).constancia(ruta_id)
    except FormacionError as e:
        raise _http(e)
    except PdfNoDisponibleError as e:
        raise HTTPException(status_code=503, detail={"codigo": "PDF_NO_DISPONIBLE", "mensaje": str(e)})
    return Response(content=pdf, media_type="application/pdf", headers={
        **_SIN_CACHE, "Content-Disposition": f'attachment; filename="{nombre}"', "X-Content-Type-Options": "nosniff",
    })
