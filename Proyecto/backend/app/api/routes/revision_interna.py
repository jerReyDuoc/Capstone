"""
HU-40 · Revisión interna del registro (modo de auditoría interna del usuario definitivo).

  GET    /api/registro-actividades/revision                              lista de verificación consolidada,
                                                                         observaciones, requisitos, periodicidad,
                                                                         revisiones anteriores y versiones
  POST   /api/registro-actividades/revision                              comienza la revisión (o retoma la en curso)
  POST   /api/registro-actividades/revision/verificaciones               {clave, criterios?, decision, nota?}
  POST   /api/registro-actividades/revision/observaciones                {clave, criterio?, prioridad, texto}
  POST   /api/registro-actividades/revision/observaciones/{id}/cerrar    {nota}
  POST   /api/registro-actividades/revision/observaciones/{id}/reabrir
  POST   /api/registro-actividades/revision/marcar                       {revisor_nombre, revisor_cargo?,
                                                                         conclusion?, huella, confirmo}
  GET    /api/registro-actividades/revision/diferencias?desde=&hasta=    diferencias entre versiones del registro
  PATCH  /api/registro-actividades/revision/configuracion                {plazo_meses, aviso_dias, recordatorio_correo}
  GET    /api/registro-actividades/revision/revisiones/{id}              una revisión (las revisadas, con su copia)
  GET    /api/registro-actividades/revision/revisiones/{id}/constancia   informe de la revisión (PDF)
  GET    /api/registro-actividades/revision/revisiones/{id}/paquete      paquete de evidencia (ZIP verificable)
  POST   /api/registro-actividades/revision/revisiones/{id}/enviar       {email?, con_paquete}
  POST   /api/registro-actividades/revision/paquetes/verificacion        multipart (file): verifica un paquete

Todas exigen usuario definitivo con contrato VIGENTE (empresa_con_servicio, HU-30): es el mismo usuario de la
empresa, sin rol ni cuenta adicional (criterio 1). Lo de otra empresa responde 404. Todo queda en el audit_log.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.revision_interna import RevisionError, RevisionInternaCasos
from app.core.config import settings
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.infrastructure.cache.limitador import Limitador, obtener_limitador

router = APIRouter(prefix="/api/registro-actividades/revision", tags=["revisión interna del registro (HU-40)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _json(datos: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(datos), status_code=status_code, headers=_SIN_CACHE)


async def _ejecutar(coro):
    try:
        return await coro
    except RevisionError as e:
        raise HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra})


def _archivo(contenido: bytes, nombre: str, mime: str, extra: dict | None = None) -> Response:
    return Response(content=contenido, media_type=mime, headers={
        **_SIN_CACHE, "Content-Disposition": f'attachment; filename="{nombre}"', "X-Content-Type-Options": "nosniff",
        **(extra or {})})


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VerificacionEntrada(_Base):
    clave: str = Field(..., min_length=3, max_length=40, pattern=r"^(actividad|elemento|flujo):\d{1,9}$")
    criterios: list[str] | None = Field(None, max_length=10, description="Vacío = todos los puntos que aplican")
    decision: Literal["verificado", "aceptado", "pendiente"]
    nota: str | None = Field(None, max_length=1000)


class ObservacionEntrada(_Base):
    clave: str = Field(..., min_length=3, max_length=40, pattern=r"^(actividad|elemento|flujo|registro):\d{1,9}$")
    criterio: str | None = Field(None, max_length=40)
    prioridad: Literal["alta", "media", "baja"] = "media"
    texto: str = Field(..., min_length=1, max_length=1000)


class CierreEntrada(_Base):
    nota: str = Field(..., min_length=1, max_length=1000)


class MarcaEntrada(_Base):
    revisor_nombre: str = Field(..., min_length=1, max_length=120)
    revisor_cargo: str | None = Field(None, max_length=120)
    conclusion: str | None = Field(None, max_length=1500)
    huella: str | None = Field(None, min_length=64, max_length=64, description="La huella del registro que se revisó")
    confirmo: bool = False


class ConfiguracionEntrada(_Base):
    plazo_meses: int = Field(..., ge=1, le=36)
    aviso_dias: int = Field(..., ge=0, le=90)
    recordatorio_correo: bool = True


class EnvioEntrada(_Base):
    email: str | None = Field(None, max_length=100, description="Vacío = el correo del usuario de la empresa")
    con_paquete: bool = False


@router.get("")
async def estado(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C1: el modo de revisión completo (lista de verificación, observaciones, requisitos y periodicidad)."""
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).estado()))


@router.post("", status_code=201)
async def iniciar(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).iniciar()), status_code=201)


@router.post("/verificaciones")
async def verificar(payload: VerificacionEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                    db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).verificar(
        payload.clave, payload.criterios or None, payload.decision, payload.nota)))


@router.post("/observaciones", status_code=201)
async def observar(payload: ObservacionEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                   db: AsyncSession = Depends(get_db)):
    """C2: una observación por actividad, elemento o flujo (o del registro completo: clave registro:0)."""
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).crear_observacion(
        payload.clave, payload.criterio, payload.prioridad, payload.texto)), status_code=201)


@router.post("/observaciones/{observacion_id}/cerrar")
async def cerrar(observacion_id: int, payload: CierreEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).cerrar_observacion(observacion_id, payload.nota)))


@router.post("/observaciones/{observacion_id}/reabrir")
async def reabrir(observacion_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).reabrir_observacion(observacion_id)))


@router.post("/marcar")
async def marcar(payload: MarcaEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db)):
    """C3: marca la versión del registro como revisada (fecha y nombre) y emite el informe con la marca."""
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).marcar(
        payload.revisor_nombre, payload.revisor_cargo, payload.conclusion, payload.huella, payload.confirmo)))


@router.get("/diferencias")
async def diferencias(desde: int | None = Query(None, ge=1), hasta: int | None = Query(None, ge=1),
                      cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C4: qué cambió entre dos versiones del registro (sin `hasta`: hasta el registro actual)."""
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).diferencias(desde, hasta)))


@router.patch("/configuracion")
async def configurar(payload: ConfiguracionEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                     db: AsyncSession = Depends(get_db)):
    """C5: plazo de la revisión periódica, aviso previo y recordatorio por correo."""
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).configurar(
        payload.plazo_meses, payload.aviso_dias, payload.recordatorio_correo)))


@router.get("/revisiones/{revision_id}")
async def detalle(revision_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).detalle(revision_id)))


@router.get("/revisiones/{revision_id}/constancia", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
async def constancia(revision_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                     db: AsyncSession = Depends(get_db)):
    contenido, nombre = await _ejecutar(RevisionInternaCasos(db, cliente).constancia(revision_id))
    return _archivo(contenido, nombre, "application/pdf")


@router.get("/revisiones/{revision_id}/paquete", response_class=Response,
            responses={200: {"content": {"application/zip": {}}}})
async def paquete(revision_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db)):
    """C4: ZIP con el informe, el historial, la lista de verificación y las observaciones, verificable con hash."""
    contenido, nombre, codigo, sha = await _ejecutar(RevisionInternaCasos(db, cliente).paquete(revision_id))
    return _archivo(contenido, nombre, "application/zip", {"X-Paquete-Codigo": codigo, "X-Paquete-Sha256": sha})


@router.post("/revisiones/{revision_id}/enviar")
async def enviar(revision_id: int, payload: EnvioEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador)):
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente, limitador).enviar(
        revision_id, payload.email, payload.con_paquete)))


@router.post("/paquetes/verificacion")
async def verificar_paquete(file: UploadFile = File(...), cliente: ClienteConServicio = Depends(empresa_con_servicio),
                            db: AsyncSession = Depends(get_db)):
    """C4: confirma que un ZIP es exactamente un paquete exportado por la empresa y que ningún archivo cambió."""
    contenido = await file.read(settings.REVISION_RAT_PAQUETE_VERIFICAR_MB * 1024 * 1024 + 1)
    return _json(await _ejecutar(RevisionInternaCasos(db, cliente).verificar_paquete(contenido)))
