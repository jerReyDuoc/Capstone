"""
HU-35 · Registro de Actividades de Tratamiento (RAT) del cliente.

  GET    /api/registro-actividades/catalogo                              bases de licitud, medidas, fuentes, plazos,
                                                                         estados, campos y textos de ayuda
  GET    /api/registro-actividades                                       actividades con su completitud y la global
  POST   /api/registro-actividades/actividades                           crea una actividad en borrador {nombre, ...}
  GET    /api/registro-actividades/actividades/{id}                      la actividad con lo que toma del mapa
  PATCH  /api/registro-actividades/actividades/{id}                      edita {revision, ...campos}
  POST   /api/registro-actividades/actividades/{id}/estado               {revision, accion}: enviar_revision |
                                                                         volver_borrador | aprobar | nueva_version |
                                                                         archivar | reactivar
  GET    /api/registro-actividades/actividades/{id}/versiones            versiones vigentes (inmutables)
  GET    /api/registro-actividades/actividades/{id}/versiones/{numero}   instantánea de una versión
  GET    /api/registro-actividades/cumplimiento                          HU-38: estado del mapa y del registro,
                                                                         matriz de mayor riesgo, brechas con su
                                                                         ruta y aporte a la evaluación
  POST   /api/registro-actividades/cumplimiento/evidencia                HU-38: usa el registro vigente y completo
                                                                         como evidencia (solo mejora controles)

Todas exigen usuario definitivo con contrato VIGENTE (empresa_con_servicio, HU-30): 401 sin sesión,
403 NO_AUTORIZADO para otros roles y 403 CONTRATO_NO_VIGENTE sin servicio. Lo de otra empresa
responde 404. Toda edición manda la `revision` de la actividad: 409 ACTIVIDAD_DESACTUALIZADA si cambió.
Dejarla vigente con datos obligatorios vacíos responde 422 ACTIVIDAD_INCOMPLETA.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.registro_actividades import RatError, RegistroActividadesCasos
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.domain.rat import catalogo as cat
from app.domain.rat.estados import ACCIONES

router = APIRouter(prefix="/api/registro-actividades", tags=["registro de actividades de tratamiento (HU-35)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _json(datos: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(datos), status_code=status_code, headers=_SIN_CACHE)


async def _ejecutar(coro):
    try:
        return await coro
    except RatError as e:
        raise HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra})


def _casos(db: AsyncSession, cliente: ClienteConServicio) -> RegistroActividadesCasos:
    return RegistroActividadesCasos(db, cliente)


# ------------------------------------------------------------------ esquemas de entrada
class _Base(BaseModel):
    # Los campos desconocidos se rechazan: un error de tipeo no debe pasar en silencio
    model_config = ConfigDict(extra="forbid")


class SeleccionEntrada(_Base):
    id: int = Field(..., ge=1)
    categorias_datos: list[str] = Field(default_factory=list, max_length=60)
    categorias_titulares: list[str] = Field(default_factory=list, max_length=60)


class FuenteEntrada(_Base):
    tipo: str = Field(..., max_length=30)
    detalle: str | None = Field(None, max_length=600)


class PlazoEntrada(_Base):
    categoria: str = Field(..., max_length=40)
    plazo: int | None = Field(None, ge=1, le=100_000)
    unidad: str | None = Field(None, max_length=10)
    desde: str | None = Field(None, max_length=30)
    fundamento: str | None = Field(None, max_length=600)


class DecisionesEntrada(_Base):
    existe: bool | None = None
    perfilamiento: bool = False
    logica: str | None = Field(None, max_length=3000)
    consecuencias: str | None = Field(None, max_length=2000)
    intervencion_humana: bool | None = None


class MedidasEntrada(_Base):
    codigos: list[str] = Field(default_factory=list, max_length=40)
    otras: str | None = Field(None, max_length=2000)


class ActividadEntrada(_Base):
    nombre: str | None = Field(None, max_length=300)
    descripcion: str | None = Field(None, max_length=2000)
    area: str | None = Field(None, max_length=240)
    elementos: list[SeleccionEntrada] | None = Field(None, max_length=200)
    flujos: list[SeleccionEntrada] | None = Field(None, max_length=200)
    finalidades: list[str] | None = Field(None, max_length=15)
    fuentes: list[FuenteEntrada] | None = Field(None, max_length=12)
    base_licitud: str | None = Field(None, max_length=30)
    interes_legitimo: str | None = Field(None, max_length=3000)
    base_sensibles: str | None = Field(None, max_length=30)
    sin_destinatarios: bool | None = None
    plazos: list[PlazoEntrada] | None = Field(None, max_length=80)
    decisiones: DecisionesEntrada | None = None
    medidas: MedidasEntrada | None = None
    rol: str | None = Field(None, max_length=20)
    responsable_mandante: str | None = Field(None, max_length=300)
    ambito_nota: str | None = Field(None, max_length=600)
    volumen: str | None = Field(None, max_length=20)      # HU-38: opcional (catalogo.VOLUMENES)


class EditarEntrada(ActividadEntrada):
    revision: int = Field(..., ge=1, description="Revisión de la actividad que vio el usuario")


class EstadoEntrada(_Base):
    revision: int = Field(..., ge=1)
    accion: Literal[ACCIONES]  # type: ignore[valid-type]


def _datos(payload: BaseModel, editar: bool) -> dict:
    """Al crear: lo que viene con valor. Al editar: solo lo enviado (null = borrar el valor)."""
    datos = payload.model_dump(exclude_unset=editar)
    datos.pop("revision", None)
    if not editar:
        datos = {k: v for k, v in datos.items() if v is not None}
    return datos


# ------------------------------------------------------------------ rutas
@router.get("/catalogo")
async def catalogo(_cliente: ClienteConServicio = Depends(empresa_con_servicio)):
    """Opciones del formulario y textos de ayuda (propuesta pendiente de validación legal)."""
    return _json(cat.catalogo_dict())


@router.get("")
async def listar(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C3: actividades con su completitud y la completitud global del registro."""
    return _json(await _casos(db, cliente).listar())


@router.post("/actividades", status_code=201)
async def crear(payload: ActividadEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).crear(_datos(payload, False))), 201)


@router.get("/actividades/{actividad_id}")
async def obtener(actividad_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).obtener(actividad_id)))


@router.patch("/actividades/{actividad_id}")
async def editar(actividad_id: int, payload: EditarEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                 db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).editar(actividad_id, _datos(payload, True), payload.revision)))


@router.post("/actividades/{actividad_id}/estado")
async def cambiar_estado(actividad_id: int, payload: EstadoEntrada,
                         cliente: ClienteConServicio = Depends(empresa_con_servicio),
                         db: AsyncSession = Depends(get_db)):
    """C4: cambia el estado. Al dejarla vigente guarda una versión inmutable."""
    return _json(await _ejecutar(_casos(db, cliente).cambiar_estado(actividad_id, payload.accion, payload.revision)))


@router.get("/actividades/{actividad_id}/versiones")
async def versiones(actividad_id: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                    db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).listar_versiones(actividad_id)))


@router.get("/actividades/{actividad_id}/versiones/{numero}")
async def version(actividad_id: int, numero: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                  db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).obtener_version(actividad_id, numero)))


# ------------------------------------------------------------------ HU-38: el registro conectado con el resto
@router.get("/cumplimiento")
async def cumplimiento(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """
    Estado del mapa y del registro, matriz de las actividades de mayor riesgo (con la evaluación de impacto
    recomendada), brechas que genera el registro con su ruta de remediación y lo que el registro aporta a
    la evaluación más reciente.
    """
    from app.application.use_cases.cumplimiento_rat import CumplimientoRegistro

    return _json(await CumplimientoRegistro(db, cliente).resumen())


@router.post("/cumplimiento/evidencia")
async def usar_como_evidencia(cliente: ClienteConServicio = Depends(empresa_con_servicio),
                              db: AsyncSession = Depends(get_db)):
    """Usa el registro vigente y completo como evidencia de los controles de protección de datos (solo mejora)."""
    from app.application.use_cases.cumplimiento_rat import CumplimientoRegistro

    return _json(await CumplimientoRegistro(db, cliente).aplicar(origen="manual"))
