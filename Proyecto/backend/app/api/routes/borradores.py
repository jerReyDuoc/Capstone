"""
HU-16 · Borradores adaptados de documentos de cumplimiento (rol cliente, contrato vigente).

  GET    /api/borradores/plantillas                    plantillas disponibles, cuota de IA y límites
  GET    /api/borradores                               borradores de la empresa (en revisión y consolidados)
  POST   /api/borradores                               genera un borrador {tipo, instrucciones?, usar_ia?, evaluacion_id?,
                                                        actividades?} (HU-38: la PIA y el aviso toman el registro)
  GET    /api/borradores/{id}                          borrador con su contenido Markdown (revisión)
  PATCH  /api/borradores/{id}                          guarda la edición {contenido, version}
  GET    /api/borradores/{id}/descarga?formato=md|pdf  descarga previa (PDF con marca "BORRADOR")
  POST   /api/borradores/{id}/consolidacion            consolida {version, confirmar_pendientes}: el PDF
                                                       queda en "Mis documentos" (HU-29)
  DELETE /api/borradores/{id}                          descarta el borrador (el PDF consolidado se queda
                                                       en "Mis documentos")

Todas exigen usuario definitivo y contrato VIGENTE (empresa_con_servicio, HU-30): 401 sin
sesión, 403 NO_AUTORIZADO para otros roles y 403 CONTRATO_NO_VIGENTE sin servicio. El PDF
consolidado se sigue descargando desde "Mis documentos" durante el plazo de gracia. Un
borrador de otra empresa responde 404.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.borradores import BorradorError, Borradores
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.infrastructure.cache.limitador import Limitador, obtener_limitador

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/borradores", tags=["borradores de cumplimiento (HU-16)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class ServiciosBorrador:
    """Lo que el caso de uso necesita de la capa de IA. Se reemplaza en las pruebas."""

    def __init__(self, agente, anonimizador, registrar_evento_factory=None):
        self.agente = agente
        self.anonimizador = anonimizador
        self.registrar_evento_factory = registrar_evento_factory


async def obtener_servicios_borrador(
    # Sesión PROPIA para métricas y auditoría de IA (como el tutor): un rollback del negocio
    # no borra la métrica de la llamada al LLM.
    sesion_ia: AsyncSession = Depends(get_db, use_cache=False),
) -> ServiciosBorrador:
    from app.application.use_cases.registrar_evento_seguridad import RegistrarEventoSeguridad
    from app.infrastructure.llm.factory import crear_agente, crear_anonimizador
    from app.infrastructure.repositories.evento_seguridad_repository import EventoSeguridadRepository
    from app.infrastructure.security.prompt_guard import ReglasPromptGuard

    try:
        agente = crear_agente(sesion_ia)
        anonimizador = crear_anonimizador()
    except Exception as e:  # noqa: BLE001 - p. ej. falta ENTITY_MAP_KEY: el borrador se arma sin IA
        logger.error("No se pudo crear la capa de IA de los borradores (%s)", type(e).__name__)
        return ServiciosBorrador(None, None)
    return ServiciosBorrador(
        agente, anonimizador,
        lambda db: RegistrarEventoSeguridad(EventoSeguridadRepository(db), ReglasPromptGuard()),
    )


def _http(e: BorradorError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra})


def _casos(db, cliente, servicios: ServiciosBorrador | None = None, limitador=None) -> Borradores:
    s = servicios or ServiciosBorrador(None, None)
    registrar = s.registrar_evento_factory(db) if s.registrar_evento_factory else None
    return Borradores(db, cliente, s.agente, s.anonimizador, limitador, registrar)


def _json(datos: dict, status_code: int = 200) -> JSONResponse:
    # jsonable_encoder: el documento consolidado (HU-29, _doc_dict) trae fechas datetime
    return JSONResponse(jsonable_encoder(datos), status_code=status_code, headers=_SIN_CACHE)


@router.get("/plantillas")
async def plantillas(
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    """C1: Política de uso de LLM, Aviso de privacidad y PIA, con sus secciones y dimensiones."""
    return _json(await _casos(db, cliente, None, limitador).catalogo())


@router.get("")
async def listar(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    return _json(await _casos(db, cliente).listar())


class NuevoBorrador(BaseModel):
    tipo: str = Field(..., max_length=30, description="politica_llm | aviso_privacidad | pia")
    # El largo real lo controla BORRADORES_MAX_CHARS_INSTRUCCIONES en el caso de uso; esto es un tope duro.
    instrucciones: str | None = Field(None, max_length=20000,
                                      description="Preferencias de redacción para el Agente IA (opcional)")
    usar_ia: bool = Field(True, description="false = solo la plantilla y la evaluación, sin llamar al LLM")
    evaluacion_id: int | None = Field(None, ge=1, description="Vacío = la evaluación más reciente de la empresa")
    # HU-38: actividades del registro que evalúa la PIA (vacío = las que tienen la evaluación recomendada)
    actividades: list[int] | None = Field(None, max_length=10,
                                          description="Ids de actividades del registro para la PIA (opcional)")


@router.post("", status_code=201)
async def generar(
    payload: NuevoBorrador,
    cliente: ClienteConServicio = Depends(empresa_con_servicio),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
    servicios: ServiciosBorrador = Depends(obtener_servicios_borrador),
):
    """C1 y C2: genera el borrador adaptado a la evaluación de tu empresa (y, si se pide, con el Agente IA)."""
    try:
        datos = await _casos(db, cliente, servicios, limitador).generar(
            payload.tipo, payload.instrucciones, payload.usar_ia, payload.evaluacion_id, payload.actividades)
    except BorradorError as e:
        raise _http(e)
    return _json(datos, 201)


@router.get("/{borrador_id}")
async def obtener(borrador_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db)):
    try:
        return _json(await _casos(db, cliente).obtener(borrador_id))
    except BorradorError as e:
        raise _http(e)


class EdicionBorrador(BaseModel):
    # Tope duro; el real es BORRADORES_MAX_CHARS_CONTENIDO
    contenido: str = Field(..., max_length=100000)
    version: int = Field(..., ge=1, description="La versión que se editó (control de edición concurrente)")


@router.patch("/{borrador_id}")
async def editar(borrador_id: int, payload: EdicionBorrador,
                 cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C3: guarda la edición del borrador en revisión."""
    try:
        return _json(await _casos(db, cliente).editar(borrador_id, payload.contenido, payload.version))
    except BorradorError as e:
        raise _http(e)


@router.get("/{borrador_id}/descarga")
async def descargar(borrador_id: int, formato: str = Query("pdf", max_length=5),
                    cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C3: descarga previa a la consolidación, en Markdown o PDF."""
    try:
        contenido, nombre, mime = await _casos(db, cliente).descargar(borrador_id, formato)
    except BorradorError as e:
        raise _http(e)
    if mime.startswith("text/"):
        mime = f"{mime}; charset=utf-8"
    return Response(content=contenido, media_type=mime, headers={
        **_SIN_CACHE, "Content-Disposition": f'attachment; filename="{nombre}"', "X-Content-Type-Options": "nosniff",
    })


class Consolidacion(BaseModel):
    version: int = Field(..., ge=1)
    confirmar_pendientes: bool = Field(False, description="Consolidar aunque queden campos [COMPLETAR: ...]")


@router.post("/{borrador_id}/consolidacion")
async def consolidar(borrador_id: int, payload: Consolidacion,
                     cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C3: consolida el borrador revisado. Queda de solo lectura y su PDF pasa a "Mis documentos"."""
    try:
        return _json(await _casos(db, cliente).consolidar(borrador_id, payload.version, payload.confirmar_pendientes))
    except BorradorError as e:
        raise _http(e)


@router.delete("/{borrador_id}", status_code=204, response_class=Response)
async def descartar(borrador_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                    db: AsyncSession = Depends(get_db)):
    try:
        await _casos(db, cliente).descartar(borrador_id)
    except BorradorError as e:
        raise _http(e)
    return Response(status_code=204)
