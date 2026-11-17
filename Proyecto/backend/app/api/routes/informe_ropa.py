"""
HU-37 · Informe RoPA desde el registro de actividades de tratamiento.

  GET    /api/registro-actividades/ropa?partes=responsable&partes=encargado
                                                       vista previa (las dos partes), datos guardados, lo que
                                                       falta para generar e historial de emisiones
  PATCH  /api/registro-actividades/ropa/datos          guarda los datos que el RoPA pide y el registro no tiene
                                                       (contacto de la empresa, delegado y organizaciones)
  POST   /api/registro-actividades/ropa                {partes?, forzar?}: genera el PDF y el XLSX con el mismo
                                                       código y los guarda en "Mis documentos" (si nada cambió,
                                                       reutiliza la última emisión)
  GET    /api/registro-actividades/ropa/{id}/descarga?formato=pdf|xlsx

Todas exigen usuario definitivo con contrato VIGENTE (empresa_con_servicio, HU-30): 401 sin sesión, 403
NO_AUTORIZADO para otros roles y 403 CONTRATO_NO_VIGENTE sin servicio. Lo de otra empresa responde 404.
Cada guardado de datos, emisión y descarga queda en el audit_log (HU-09). Sin contrato vigente, los
informes ya emitidos siguen disponibles en "Mis documentos".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ropa.casos_uso.generar_informe_ropa import InformeRopaCasos, InformeRopaError
from app.core.database import get_db
from app.api.dependencias.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.api.schemas.informe_ropa_esquemas import DatosEntrada, EmitirEntrada

router = APIRouter(prefix="/api/registro-actividades/ropa", tags=["informe RoPA del registro (HU-37)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _json(datos: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(datos), status_code=status_code, headers=_SIN_CACHE)


async def _ejecutar(coro):
    try:
        return await coro
    except InformeRopaError as e:
        raise HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra})


def _partes_validas(partes: list[str] | None) -> list[str]:
    partes = list(partes or [])
    invalidas = [p for p in partes if p not in ("responsable", "encargado")]
    if invalidas or len(partes) > 2:
        raise HTTPException(status_code=422, detail={"codigo": "PARTE_INVALIDA",
                                                     "mensaje": "Elige «Como responsable», «Como encargado» o ambas."})
    return partes


@router.get("")
async def listar(partes: list[str] | None = Query(None),
                 cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """Vista previa, datos guardados, lo que falta e historial de emisiones."""
    return _json(await _ejecutar(InformeRopaCasos(db, cliente).listar(_partes_validas(partes))))


@router.patch("/datos")
async def guardar_datos(payload: DatosEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                        db: AsyncSession = Depends(get_db)):
    """C3: guarda los datos que el RoPA pide y el registro no tiene (solo cambian los campos enviados)."""
    entrada = payload.model_dump(exclude_unset=True)
    return _json(await _ejecutar(InformeRopaCasos(db, cliente).guardar_datos(entrada)))


@router.post("", status_code=201)
async def emitir(payload: EmitirEntrada | None = None, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db)):
    """C1–C4: genera el PDF y el XLSX con el mismo código y los guarda en Mis documentos."""
    partes = _partes_validas(payload.partes if payload else [])
    r = await _ejecutar(InformeRopaCasos(db, cliente).emitir(partes, bool(payload and payload.forzar)))
    return _json(r, status_code=200 if r["reutilizado"] else 201)


@router.get("/{informe_id}/descarga", response_class=Response,
            responses={200: {"content": {"application/pdf": {},
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}})
async def descargar(informe_id: int, formato: str = Query("pdf", pattern="^(pdf|xlsx)$"),
                    cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C4: el PDF o la planilla de una emisión (la descarga queda en el audit_log)."""
    contenido, nombre, mime = await _ejecutar(InformeRopaCasos(db, cliente).descargar(informe_id, formato))
    return Response(content=contenido, media_type=mime, headers={
        **_SIN_CACHE, "Content-Disposition": f'attachment; filename="{nombre}"', "X-Content-Type-Options": "nosniff"})
