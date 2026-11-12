"""
HU-36 · Informe del Registro de Actividades de Tratamiento (RAT).

  GET   /api/registro-actividades/informes                          vista previa (oficial o borrador y por qué),
                                                                    última emisión e historial de emisiones
  POST  /api/registro-actividades/informes                          {forzar?}: genera el PDF y el XLSX con el mismo
                                                                    código y los guarda en "Mis documentos" (si el
                                                                    registro no cambió, reutiliza la última emisión)
  GET   /api/registro-actividades/informes/verificacion?codigo=…    confirma un código verificable de la empresa
  GET   /api/registro-actividades/informes/{id}/descarga?formato=pdf|xlsx
  POST  /api/registro-actividades/informes/{id}/enviar              {email?, formatos: ["pdf", "xlsx"]}

Todas exigen usuario definitivo con contrato VIGENTE (empresa_con_servicio, HU-30): 401 sin sesión, 403
NO_AUTORIZADO para otros roles y 403 CONTRATO_NO_VIGENTE sin servicio. Lo de otra empresa responde 404.
Cada emisión, descarga, envío y verificación queda en el audit_log (HU-09). Sin contrato vigente, los
informes ya emitidos siguen disponibles en "Mis documentos" (HU-29/HU-30).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.informe_rat import FORMATOS, InformeRatCasos, InformeRatError
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.infrastructure.cache.limitador import Limitador, obtener_limitador

router = APIRouter(prefix="/api/registro-actividades/informes", tags=["informe del registro de actividades (HU-36)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _json(datos: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(datos), status_code=status_code, headers=_SIN_CACHE)


async def _ejecutar(coro):
    try:
        return await coro
    except InformeRatError as e:
        raise HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra})


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmitirEntrada(_Base):
    forzar: bool = Field(False, description="Emitir aunque el registro no haya cambiado desde la última emisión")


class EnviarEntrada(_Base):
    email: str | None = Field(None, max_length=100, description="Vacío = el correo del usuario de la empresa")
    formatos: list[str] = Field(default_factory=lambda: list(FORMATOS), min_length=1, max_length=2)


@router.get("")
async def listar(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """Vista previa del informe (oficial o borrador y por qué) y el historial de emisiones."""
    return _json(await _ejecutar(InformeRatCasos(db, cliente).listar()))


@router.post("", status_code=201)
async def emitir(payload: EmitirEntrada | None = None, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db)):
    """C1–C4: genera el PDF y el XLSX con el mismo código verificable y los guarda en Mis documentos."""
    r = await _ejecutar(InformeRatCasos(db, cliente).emitir(bool(payload and payload.forzar)))
    return _json(r, status_code=200 if r["reutilizado"] else 201)


@router.get("/verificacion")
async def verificar(codigo: str = Query(..., min_length=10, max_length=40),
                    cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C2: confirma que un código verificable corresponde a un informe de la empresa y si el registro sigue igual."""
    return _json(await _ejecutar(InformeRatCasos(db, cliente).verificar(codigo)))


@router.get("/{informe_id}/descarga", response_class=Response,
            responses={200: {"content": {"application/pdf": {},
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}})
async def descargar(informe_id: int, formato: str = Query("pdf", pattern="^(pdf|xlsx)$"),
                    cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C3: el PDF o la planilla de una emisión (la descarga queda en el audit_log)."""
    contenido, nombre, mime = await _ejecutar(InformeRatCasos(db, cliente).descargar(informe_id, formato))
    return Response(content=contenido, media_type=mime, headers={
        **_SIN_CACHE, "Content-Disposition": f'attachment; filename="{nombre}"', "X-Content-Type-Options": "nosniff"})


@router.post("/{informe_id}/enviar")
async def enviar(informe_id: int, payload: EnviarEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador)):
    """Envía la emisión por correo (por defecto, al correo del usuario de la empresa), con los formatos elegidos."""
    invalidos = [f for f in payload.formatos if f not in FORMATOS]
    if invalidos:
        raise HTTPException(status_code=422, detail={"codigo": "FORMATO_INVALIDO", "mensaje": "Elige PDF, Excel o ambos."})
    return _json(await _ejecutar(InformeRatCasos(db, cliente, limitador).enviar(informe_id, payload.email,
                                                                               payload.formatos)))
