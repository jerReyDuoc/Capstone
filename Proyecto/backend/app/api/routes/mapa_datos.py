"""
HU-34 · Mapa de datos personales del cliente (base del RAT y del RoPA).

  GET    /api/mapa-datos/catalogo                         catálogo común con el RAT (categorías, titulares, países…)
  GET    /api/mapa-datos                                  el mapa: elementos, flujos, resumen, hallazgos y completitud
  POST   /api/mapa-datos/elementos                        agrega un sistema, base de datos o tercero {version, ...}
  PATCH  /api/mapa-datos/elementos/{id}                   edita un elemento {version, ...campos}
  DELETE /api/mapa-datos/elementos/{id}?version=N         elimina un elemento (y sus flujos)
  POST   /api/mapa-datos/flujos                           agrega un flujo {version, origen_id, destino_id, ...}
  PATCH  /api/mapa-datos/flujos/{id}                      edita un flujo
  DELETE /api/mapa-datos/flujos/{id}?version=N            elimina un flujo
  POST   /api/mapa-datos/revision                         confirma lo que vino de plantillas o sugerencias
  GET    /api/mapa-datos/plantillas                       plantillas por rubro (la del rubro, recomendada)
  POST   /api/mapa-datos/plantillas/aplicar               {codigo, version}: agrega lo que falte de la plantilla
  GET    /api/mapa-datos/sugerencias                      propuestas según las respuestas de la evaluación
  POST   /api/mapa-datos/sugerencias/{clave}/aceptar      {version, origen_id?}
  POST   /api/mapa-datos/sugerencias/{clave}/descartar
  POST   /api/mapa-datos/sugerencias/restablecer          vuelve a mostrar las descartadas
  GET    /api/mapa-datos/versiones?pagina=N               historial de versiones (criterio 5)
  GET    /api/mapa-datos/versiones/{numero}               instantánea y cambios de una versión
  POST   /api/mapa-datos/versiones/{numero}/restaurar     {version}: vuelve a esa versión (crea una nueva)
  GET    /api/mapa-datos/informe/pdf?sensibles&nna&internacional&tercero&pais&tipo
  POST   /api/mapa-datos/informe/enviar                   el mismo PDF por correo {email?, filtros…}

Todas exigen usuario definitivo con contrato VIGENTE (empresa_con_servicio, HU-30): 401 sin sesión,
403 NO_AUTORIZADO para otros roles y 403 CONTRATO_NO_VIGENTE sin servicio. Lo de otra empresa
responde 404. Toda edición manda la `version` que vio el usuario: 409 MAPA_DESACTUALIZADO si cambió.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.informes import correo
from app.application.use_cases.limites_encuesta import ventana_diaria
from app.application.use_cases.mapa_datos import MapaDatosCasos, MapaDatosError
from app.core.config import settings
from app.core.database import get_db
from app.core.servicio_pagado import ClienteConServicio, empresa_con_servicio
from app.domain import catalogo_tratamiento as cat
from app.domain.mapa_datos import analisis
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador
from app.infrastructure.repositories.bitacora_repository import Accion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mapa-datos", tags=["mapa de datos personales (HU-34)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _http(e: MapaDatosError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensaje": e.mensaje, **e.extra})


def _json(datos: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(datos), status_code=status_code, headers=_SIN_CACHE)


def _casos(db: AsyncSession, cliente: ClienteConServicio, limitador=None) -> MapaDatosCasos:
    return MapaDatosCasos(db, cliente, limitador)


async def _ejecutar(coro):
    try:
        return await coro
    except MapaDatosError as e:
        raise _http(e)


# ------------------------------------------------------------------ esquemas de entrada
class _Base(BaseModel):
    # Los campos desconocidos se rechazan: un error de tipeo no debe pasar en silencio
    model_config = ConfigDict(extra="forbid")


class ElementoEntrada(_Base):
    version: int = Field(..., ge=0, description="Versión del mapa que vio el usuario")
    tipo: str | None = Field(None, max_length=20)
    subtipo: str | None = Field(None, max_length=30)
    nombre: str | None = Field(None, max_length=200)
    descripcion: str | None = Field(None, max_length=800)
    proveedor: str | None = Field(None, max_length=200)
    pais: str | None = Field(None, max_length=2)
    responsable: str | None = Field(None, max_length=200)
    categorias_datos: list[str] | None = Field(None, max_length=60)
    categorias_titulares: list[str] | None = Field(None, max_length=60)
    nna_declarado: bool | None = None
    rol_tercero: str | None = Field(None, max_length=20)
    contrato_firmado: bool | None = None
    pendiente_revision: bool | None = None


class FlujoEntrada(_Base):
    version: int = Field(..., ge=0)
    origen_id: int | None = Field(None, ge=1)
    destino_id: int | None = Field(None, ge=1)
    finalidad: str | None = Field(None, max_length=500)
    categorias_datos: list[str] | None = Field(None, max_length=60)
    categorias_titulares: list[str] | None = Field(None, max_length=60)
    nna_declarado: bool | None = None
    frecuencia: str | None = Field(None, max_length=20)
    medio: str | None = Field(None, max_length=20)
    cifrado: bool | None = None
    garantia: str | None = Field(None, max_length=30)
    pendiente_revision: bool | None = None


def _datos(payload: BaseModel, editar: bool) -> dict:
    """Campos enviados (sin la versión). Al editar, solo lo que vino en el cuerpo (null = borrar el valor)."""
    datos = payload.model_dump(exclude_unset=editar)
    datos.pop("version", None)
    if not editar:
        datos = {k: v for k, v in datos.items() if v is not None}
    return datos


class VersionEntrada(_Base):
    version: int = Field(..., ge=0)


class RevisionEntrada(_Base):
    version: int = Field(..., ge=0)
    todo: bool = False
    elementos: list[int] | None = Field(None, max_length=2000)
    flujos: list[int] | None = Field(None, max_length=5000)


class PlantillaEntrada(_Base):
    version: int = Field(..., ge=0)
    codigo: str = Field(..., max_length=30)


class AceptarSugerenciaEntrada(_Base):
    version: int = Field(..., ge=0)
    origen_id: int | None = Field(None, ge=1)


class EnviarInformeEntrada(_Base):
    email: str | None = Field(None, max_length=100, description="Vacío = el correo del usuario de la empresa")
    sensibles: bool = False
    nna: bool = False
    internacional: bool = False
    tercero: int | None = Field(None, ge=1)
    pais: str | None = Field(None, max_length=2)
    tipo: str | None = Field(None, max_length=20)


# ------------------------------------------------------------------ catálogo y mapa
@router.get("/catalogo")
async def catalogo(_cliente: ClienteConServicio = Depends(empresa_con_servicio)):
    """C2: catálogo común con el RAT (categorías de datos con las sensibles, titulares con NNA, países…)."""
    return _json(cat.catalogo_dict())


@router.get("")
async def obtener(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """El mapa completo con sus transferencias calculadas, el resumen, los hallazgos de riesgo y la completitud."""
    return _json(await _casos(db, cliente).vista())


# ------------------------------------------------------------------ elementos
@router.post("/elementos", status_code=201)
async def crear_elemento(payload: ElementoEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                         db: AsyncSession = Depends(get_db)):
    """C1/C2: agrega un sistema, una base de datos o un tercero."""
    return _json(await _ejecutar(_casos(db, cliente).crear_elemento(_datos(payload, False), payload.version)), 201)


@router.patch("/elementos/{elemento_id}")
async def editar_elemento(elemento_id: int, payload: ElementoEntrada,
                          cliente: ClienteConServicio = Depends(empresa_con_servicio),
                          db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).editar_elemento(elemento_id, _datos(payload, True),
                                                                     payload.version)))


@router.delete("/elementos/{elemento_id}")
async def eliminar_elemento(elemento_id: int, version: int = Query(..., ge=0),
                            cliente: ClienteConServicio = Depends(empresa_con_servicio),
                            db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).eliminar_elemento(elemento_id, version)))


# ------------------------------------------------------------------ flujos
@router.post("/flujos", status_code=201)
async def crear_flujo(payload: FlujoEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                      db: AsyncSession = Depends(get_db)):
    """C1: flujo entre elementos (si cambia el país del destino, es una transferencia internacional)."""
    return _json(await _ejecutar(_casos(db, cliente).crear_flujo(_datos(payload, False), payload.version)), 201)


@router.patch("/flujos/{flujo_id}")
async def editar_flujo(flujo_id: int, payload: FlujoEntrada,
                       cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).editar_flujo(flujo_id, _datos(payload, True), payload.version)))


@router.delete("/flujos/{flujo_id}")
async def eliminar_flujo(flujo_id: int, version: int = Query(..., ge=0),
                         cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).eliminar_flujo(flujo_id, version)))


@router.post("/revision")
async def confirmar_revision(payload: RevisionEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                             db: AsyncSession = Depends(get_db)):
    """Confirma lo que se agregó desde una plantilla o una sugerencia (deja de estar "por confirmar")."""
    return _json(await _ejecutar(_casos(db, cliente).confirmar_revision(
        payload.version, payload.elementos, payload.flujos, payload.todo)))


# ------------------------------------------------------------------ plantillas y sugerencias (C4)
@router.get("/plantillas")
async def plantillas(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    return _json(await _casos(db, cliente).plantillas())


@router.post("/plantillas/aplicar")
async def aplicar_plantilla(payload: PlantillaEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                            db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).aplicar_plantilla(payload.codigo, payload.version)))


@router.get("/sugerencias")
async def sugerencias(cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db)):
    """C4: propuestas a partir de cómo declaró usar la IA la empresa en su evaluación más reciente."""
    return _json(await _casos(db, cliente).sugerencias())


@router.post("/sugerencias/restablecer")
async def restablecer_sugerencias(cliente: ClienteConServicio = Depends(empresa_con_servicio),
                                  db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).descartar_sugerencia("", restablecer=True)))


@router.post("/sugerencias/{clave}/aceptar")
async def aceptar_sugerencia(clave: str, payload: AceptarSugerenciaEntrada,
                             cliente: ClienteConServicio = Depends(empresa_con_servicio),
                             db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).aceptar_sugerencia(clave[:40], payload.version,
                                                                        payload.origen_id)))


@router.post("/sugerencias/{clave}/descartar")
async def descartar_sugerencia(clave: str, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                               db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).descartar_sugerencia(clave[:40])))


# ------------------------------------------------------------------ versiones (C5)
@router.get("/versiones")
async def listar_versiones(pagina: int = Query(1, ge=1, le=100000),
                           cliente: ClienteConServicio = Depends(empresa_con_servicio),
                           db: AsyncSession = Depends(get_db)):
    return _json(await _casos(db, cliente).listar_versiones(pagina))


@router.get("/versiones/{numero}")
async def obtener_version(numero: int, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                          db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).obtener_version(numero)))


@router.post("/versiones/{numero}/restaurar")
async def restaurar_version(numero: int, payload: VersionEntrada,
                            cliente: ClienteConServicio = Depends(empresa_con_servicio),
                            db: AsyncSession = Depends(get_db)):
    return _json(await _ejecutar(_casos(db, cliente).restaurar_version(numero, payload.version)))


# ------------------------------------------------------------------ informe (C3)
def _pdf(datos) -> bytes:
    from app.application.mapa_datos.pdf_mapa import PdfNoDisponibleError, generar_pdf_mapa

    try:
        return generar_pdf_mapa(datos)
    except PdfNoDisponibleError as e:
        raise HTTPException(status_code=503, detail={"codigo": "PDF_NO_DISPONIBLE", "mensaje": str(e)})


@router.get("/informe/pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
async def descargar_informe(
    sensibles: str | None = Query(None, max_length=5), nna: str | None = Query(None, max_length=5),
    internacional: str | None = Query(None, max_length=5), tercero: str | None = Query(None, max_length=12),
    pais: str | None = Query(None, max_length=2), tipo: str | None = Query(None, max_length=20),
    cliente: ClienteConServicio = Depends(empresa_con_servicio), db: AsyncSession = Depends(get_db),
):
    """C3: informe PDF del mapa con los mismos filtros del mapa navegable."""
    from app.application.mapa_datos.pdf_mapa import nombre_archivo

    casos = _casos(db, cliente)
    filtros = analisis.parsear_filtros(sensibles, nna, internacional, tercero, pais, tipo)
    datos = await _ejecutar(casos.datos_informe(filtros))
    contenido = _pdf(datos)
    casos.registrar_informe(Accion.MAPA_INFORME_DESCARGADO, datos.version, filtros)
    await db.commit()
    return Response(content=contenido, media_type="application/pdf", headers={
        **_SIN_CACHE, "Content-Disposition": f'attachment; filename="{nombre_archivo(datos.version, datos.generado)}"',
        "X-Content-Type-Options": "nosniff",
    })


@router.post("/informe/enviar")
async def enviar_informe(payload: EnviarInformeEntrada, cliente: ClienteConServicio = Depends(empresa_con_servicio),
                         db: AsyncSession = Depends(get_db), limitador: Limitador = Depends(obtener_limitador)):
    """C3: envía el informe PDF del mapa por correo (por defecto, al correo del usuario de la empresa)."""
    from app.application.mapa_datos.pdf_mapa import cuerpo_correo, nombre_archivo

    def error(status: int, codigo: str, mensaje: str, **extra):
        return HTTPException(status_code=status, detail={"codigo": codigo, "mensaje": mensaje, **extra})

    if settings.CORREO_MODO == "desactivado":
        raise error(503, "CORREO_NO_DISPONIBLE", "El envío por correo no está habilitado. Descarga el PDF.")
    casos = _casos(db, cliente, limitador)
    destino = (payload.email or "").strip().lower() or casos.email_usuario
    if not correo.EMAIL_VALIDO.match(destino or ""):
        raise error(422, "EMAIL_INVALIDO", "Revisa el formato del correo (ejemplo: nombre@empresa.cl).")
    filtros = analisis.parsear_filtros(payload.sensibles, payload.nna, payload.internacional, payload.tercero,
                                       payload.pais, payload.tipo)
    datos = await _ejecutar(casos.datos_informe(filtros))          # 409 si el mapa está vacío (antes del cupo)

    fecha, ventana, _ = ventana_diaria()
    clave = f"mapa:correo:{casos.empresa_id}:{fecha}"
    try:
        consumo = await limitador.consumir(clave, settings.MAPA_CORREOS_DIA_EMPRESA, ventana)
    except LimitadorNoDisponibleError:
        raise error(503, "LIMITADOR_NO_DISPONIBLE", "No pudimos enviar el correo ahora. Descarga el PDF.")
    if not consumo.permitido:
        await limitador.devolver(clave)
        raise error(429, "LIMITE_CORREOS", f"Ya enviaste el informe {settings.MAPA_CORREOS_DIA_EMPRESA} veces hoy. "
                    "Descárgalo o vuelve a intentarlo mañana.", reintentar_en_s=consumo.reintentar_en_s)
    try:
        pdf = _pdf(datos)
        res = analisis.resumen(datos.elementos, datos.flujos)
        cuenta = analisis.contar_hallazgos(analisis.hallazgos(datos.elementos, datos.flujos))
        completitud = analisis.completitud(datos.elementos, datos.flujos)["porcentaje"]
        texto, html = cuerpo_correo(datos.razon_social, datos.version, res, cuenta, completitud)
        modo = await correo.enviar(
            destino, f"Mapa de datos personales · versión {datos.version}", texto, html,
            [correo.Adjunto(nombre_archivo(datos.version, datos.generado), pdf)])
    except (correo.CorreoFallidoError, correo.CorreoNoDisponibleError, HTTPException) as e:
        await limitador.devolver(clave)
        if isinstance(e, HTTPException):
            raise
        logger.warning("[mapa_datos] envío fallido empresa %s: %s", casos.empresa_id, e)
        raise error(502 if isinstance(e, correo.CorreoFallidoError) else 503, "CORREO_FALLIDO",
                    "No pudimos enviar el correo. Inténtalo de nuevo en unos minutos o descarga el PDF.")
    casos.registrar_informe(Accion.MAPA_INFORME_ENVIADO, datos.version, filtros, modo=modo,
                            destino_propio=destino == casos.email_usuario)
    await db.commit()
    logger.info("[mapa_datos] informe v%s enviado a %s (%s)", datos.version, correo.enmascarar(destino), modo)
    return _json({"enviado": True, "destino": correo.enmascarar(destino), "modo": modo})
