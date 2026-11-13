"""
HU-41 · Registro de tratamiento de la propia plataforma (solo admin_therion).

  GET   /api/admin/privacidad-plataforma                          registro generado del inventario: actividades,
                                                                 mapa, proveedores, plazos vigentes, revisión
                                                                 interna, datos del RoPA y emisiones
  GET   /api/admin/privacidad-plataforma/actividades/{clave}      ficha de una actividad
  PATCH /api/admin/privacidad-plataforma/ropa-datos               datos de contacto de Therion Labs para el RoPA
  POST  /api/admin/privacidad-plataforma/informes                 {tipo: rat|ropa, forzar?}: PDF y Excel
  GET   /api/admin/privacidad-plataforma/informes/verificacion?codigo=…
  GET   /api/admin/privacidad-plataforma/informes/{id}/descarga?formato=pdf|xlsx
  GET   /api/admin/privacidad-plataforma/mapa/descarga            PDF del mapa de datos de la plataforma

401 sin sesión y 403 con otro rol (solo_admin). Cada emisión, descarga, verificación y cambio de los datos del
RoPA queda en el audit_log (HU-09), sin los datos de contacto.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.privacidad_plataforma import PrivacidadPlataformaCasos, PrivacidadPlataformaError
from app.core.alcance import solo_admin
from app.core.autenticacion import Actor
from app.core.database import get_db

router = APIRouter(prefix="/api/admin/privacidad-plataforma", tags=["admin · privacidad de la plataforma (HU-41)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _json(datos: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(datos), status_code=status_code, headers=_SIN_CACHE)


async def _ejecutar(coro):
    try:
        return await coro
    except PrivacidadPlataformaError as e:
        raise HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra})


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmitirEntrada(_Base):
    tipo: str = Field(..., pattern="^(rat|ropa)$")
    forzar: bool = False


class DatosRopaEntrada(_Base):
    direccion: str | None = Field(None, max_length=200)
    correo: str | None = Field(None, max_length=100)
    telefono: str | None = Field(None, max_length=25)
    tiene_dpo: bool | None = None
    dpo_cargo: str | None = Field(None, max_length=120)
    dpo_correo: str | None = Field(None, max_length=100)


def _archivo(contenido: bytes, nombre: str, mime: str) -> Response:
    return Response(content=contenido, media_type=mime, headers={
        **_SIN_CACHE, "Content-Disposition": f'attachment; filename="{nombre}"', "X-Content-Type-Options": "nosniff"})


@router.get("")
async def resumen(actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """El registro generado del inventario con la revisión interna y las emisiones."""
    return _json(await _ejecutar(PrivacidadPlataformaCasos(db, actor).resumen()))


@router.get("/actividades/{clave}")
async def actividad(clave: str, actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(PrivacidadPlataformaCasos(db, actor).actividad(clave[:60])))


@router.patch("/ropa-datos")
async def guardar_ropa_datos(payload: DatosRopaEntrada, actor: Actor = Depends(solo_admin),
                             db: AsyncSession = Depends(get_db)):
    """Solo cambian los campos enviados (null borra el valor). Mismas reglas que el RoPA del cliente."""
    entrada = payload.model_dump(exclude_unset=True)
    return _json(await _ejecutar(PrivacidadPlataformaCasos(db, actor).guardar_ropa_datos(entrada)))


@router.post("/informes", status_code=201)
async def emitir(payload: EmitirEntrada, actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Genera el PDF y el Excel con el mismo código verificable (200 si se reutiliza la última emisión)."""
    r = await _ejecutar(PrivacidadPlataformaCasos(db, actor).emitir(payload.tipo, payload.forzar))
    return _json(r, status_code=200 if r["reutilizado"] else 201)


@router.get("/informes/verificacion")
async def verificar(codigo: str = Query(..., min_length=10, max_length=45), actor: Actor = Depends(solo_admin),
                    db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(PrivacidadPlataformaCasos(db, actor).verificar(codigo)))


@router.get("/informes/{informe_id}/descarga", response_class=Response,
            responses={200: {"content": {"application/pdf": {},
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}}}})
async def descargar(informe_id: int, formato: str = Query("pdf", pattern="^(pdf|xlsx)$"),
                    actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    contenido, nombre, mime = await _ejecutar(PrivacidadPlataformaCasos(db, actor).descargar(informe_id, formato))
    return _archivo(contenido, nombre, mime)


@router.get("/mapa/descarga", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
async def descargar_mapa(actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    contenido, nombre = await _ejecutar(PrivacidadPlataformaCasos(db, actor).pdf_mapa())
    return _archivo(contenido, nombre, "application/pdf")
