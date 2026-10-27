"""
HU-27 · Panel interno (HU-28): empresas cliente, usuario definitivo y migración.

Todas las rutas son solo de admin_therion (401 sin token, 403 con otro rol).

  Solicitudes de contratación (base HU-31)
    GET   /api/admin/contrataciones?estado=&page=&size=
    GET   /api/admin/contrataciones/{id}
    PATCH /api/admin/contrataciones/{id}                  {estado: contratada|pendiente|descartada}

  Empresas cliente (HU-27)
    POST  /api/admin/empresas                             alta: empresa + usuario + migración + enlace
    GET   /api/admin/empresas
    GET   /api/admin/empresas/{id}
    POST  /api/admin/empresas/{id}/evaluaciones           asociar más evaluaciones autorizadas
    POST  /api/admin/empresas/{id}/usuario/activacion     reenviar el enlace (revoca el anterior)

  Bitácora (base HU-09)
    GET   /api/admin/bitacora?entidad=&entidad_id=&accion=&page=&size=

El admin nunca ve ni define la contraseña del cliente, ni recibe el token de activación:
el enlace solo va al correo del usuario definitivo.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.activacion_cuenta import ResultadoCorreo
from app.application.use_cases.contratacion_empresa import (
    ContratacionError, DatosEmpresa, DatosUsuario, EmpresasClienteUseCase, SolicitudesContratacionUseCase,
)
from app.application.use_cases.migrar_evaluacion import EvaluacionMigrada, MigracionError
from app.core.alcance import solo_admin
from app.core.autenticacion import Actor
from app.core.database import get_db
from app.domain.models.empresa import Empresa
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.resumen import Resumen
from app.domain.models.rubro import Rubro
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.domain.models.usuario_definitivo import UsuarioDefinitivo
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.repositories.bitacora_repository import BitacoraRepository

router = APIRouter(prefix="/api/admin", tags=["admin · empresas cliente (HU-27)"])


def _error(e: ContratacionError | MigracionError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": str(e), **e.extra})


# ------------------------------------------------------------------ esquemas
class CambiarEstadoRequest(BaseModel):
    estado: str = Field(..., max_length=20)


class EmpresaRequest(BaseModel):
    razon_social: str = Field(..., max_length=200)
    rut: str = Field(..., max_length=20)
    rubro_id: int = Field(..., ge=1)
    fecha_inicio_contrato: date
    fecha_termino_contrato: date


class UsuarioRequest(BaseModel):
    nombre: str = Field(..., max_length=200)
    email: str = Field(..., max_length=200)


class AltaEmpresaRequest(BaseModel):
    empresa: EmpresaRequest
    usuario: UsuarioRequest
    solicitudes_ids: list[int] = Field(..., min_length=1, max_length=20)


class AsociarRequest(BaseModel):
    solicitudes_ids: list[int] = Field(..., min_length=1, max_length=20)


# ------------------------------------------------------------------ serialización
async def _datos_evaluacion(db: AsyncSession, evaluacion_id: int) -> dict:
    fila = (await db.execute(
        select(Evaluacion, Rubro.id, Rubro.nombre_rubro)
        .outerjoin(UsuarioTemporal, Evaluacion.usuario_temporal_id == UsuarioTemporal.id)
        .outerjoin(Rubro, UsuarioTemporal.rubro_id == Rubro.id)
        .where(Evaluacion.id == evaluacion_id)
    )).first()
    if fila is None:
        return {"id": evaluacion_id}
    ev, rubro_id, rubro = fila
    puntaje = await db.scalar(select(func.avg(Resumen.puntaje_obtenido)).where(Resumen.evaluacion_id == ev.id))
    return {
        "id": ev.id, "origen": ev.origen, "estado_progreso": ev.estado_progreso,
        "fecha_inicio": ev.fecha_inicio, "completada": ev.esta_cerrada,
        "rubro_id": rubro_id, "rubro": rubro,
        "puntaje_general": round(puntaje, 1) if puntaje is not None else None,
        "empresa_id": ev.empresa_id, "fecha_migracion": ev.fecha_migracion,
    }


async def _solicitud(db: AsyncSession, s: SolicitudContratacion) -> dict:
    return {
        "id": s.id, "estado": s.estado,
        "contacto": {"nombre": s.nombre_contacto, "email": s.email_contacto, "telefono": s.telefono_contacto},
        "razon_social_declarada": s.razon_social_declarada,
        "autoriza_migracion": s.autoriza_migracion, "consentimiento_version": s.consentimiento_version,
        "fecha_autorizacion": s.fecha_autorizacion, "fecha_creacion": s.fecha_creacion,
        "fecha_actualizacion": s.fecha_actualizacion, "fecha_migracion": s.fecha_migracion,
        "empresa_id": s.empresa_id,
        "evaluacion": await _datos_evaluacion(db, s.evaluacion_id),
    }


def _empresa(e: Empresa) -> dict:
    return {
        "id": e.id, "razon_social": e.razon_social, "rut": e.rut, "rubro_id": e.rubro_id,
        "fecha_inicio_contrato": e.fecha_inicio_contrato, "fecha_termino_contrato": e.fecha_termino_contrato,
        "contrato_vigente": e.contrato_vigente(), "fecha_creacion": e.fecha_creacion,
    }


def _usuario(u: UsuarioDefinitivo | None) -> dict | None:
    if u is None:
        return None
    return {  # nunca el hash ni tokens
        "id": u.id, "nombre": u.nombre, "email": u.email, "rol": u.rol, "estado": u.estado,
        "fecha_creacion": u.fecha_creacion, "fecha_activacion": u.fecha_activacion, "ultimo_acceso": u.ultimo_acceso,
    }


def _correo(r: ResultadoCorreo | None) -> dict | None:
    if r is None:
        return None
    mensaje = (
        "Enlace de activación enviado al correo del usuario." if r.enviado and r.modo == "smtp" else
        "Enlace guardado como .eml en STORAGE_DIR/correos (CORREO_MODO=archivo, solo desarrollo)."
        if r.enviado else
        "No se pudo enviar el enlace de activación: reenvíalo cuando el correo esté disponible."
    )
    return {"enviado": r.enviado, "modo": r.modo, "motivo": r.motivo, "mensaje": mensaje}


def _migradas(migradas: list[EvaluacionMigrada]) -> list[dict]:
    return [m.como_dict() for m in migradas]


# ------------------------------------------------------------------ solicitudes (HU-31 base)
@router.get("/contrataciones")
async def listar_contrataciones(
    estado: str | None = Query(None, description="pendiente | contratada | migrada | descartada"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        filas, total = await SolicitudesContratacionUseCase(db).listar(estado, page, size)
    except ContratacionError as e:
        raise _error(e)
    return {"items": [await _solicitud(db, s) for s in filas], "total": total, "page": page, "size": size}


@router.get("/contrataciones/{solicitud_id}")
async def obtener_contratacion(solicitud_id: int, _: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    try:
        s = await SolicitudesContratacionUseCase(db).obtener(solicitud_id)
    except ContratacionError as e:
        raise _error(e)
    return await _solicitud(db, s)


@router.patch("/contrataciones/{solicitud_id}")
async def cambiar_estado_contratacion(
    solicitud_id: int, payload: CambiarEstadoRequest,
    actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db),
):
    """Marca la solicitud como contratada (acuerdo cerrado), pendiente o descartada."""
    try:
        s = await SolicitudesContratacionUseCase(db).cambiar_estado(actor, solicitud_id, payload.estado)
    except ContratacionError as e:
        raise _error(e)
    return await _solicitud(db, s)


# ------------------------------------------------------------------ empresas (HU-27)
@router.post("/empresas", status_code=201)
async def alta_empresa(payload: AltaEmpresaRequest, actor: Actor = Depends(solo_admin),
                       db: AsyncSession = Depends(get_db)):
    """
    Crea la empresa y su usuario definitivo (rol cliente), migra en la misma transacción
    las evaluaciones de las solicitudes indicadas y envía el enlace de activación.
    """
    e, u = payload.empresa, payload.usuario
    try:
        r = await EmpresasClienteUseCase(db).crear(
            actor,
            DatosEmpresa(razon_social=e.razon_social, rut=e.rut, rubro_id=e.rubro_id,
                         fecha_inicio_contrato=e.fecha_inicio_contrato,
                         fecha_termino_contrato=e.fecha_termino_contrato),
            DatosUsuario(nombre=u.nombre, email=u.email),
            payload.solicitudes_ids,
        )
    except (ContratacionError, MigracionError) as err:
        raise _error(err)
    return {
        "empresa": _empresa(r.empresa), "usuario": _usuario(r.usuario),
        "evaluaciones_migradas": _migradas(r.migradas), "activacion": _correo(r.correo),
    }


@router.get("/empresas")
async def listar_empresas(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                          _: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    filas, total = await EmpresasClienteUseCase(db).listar(page, size)
    return {
        "items": [{**_empresa(e), "usuario": _usuario(u), "evaluaciones": n} for e, u, n in filas],
        "total": total, "page": page, "size": size,
    }


@router.get("/empresas/{empresa_id}")
async def detalle_empresa(empresa_id: int, _: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    try:
        e, u, evaluaciones = await EmpresasClienteUseCase(db).detalle(empresa_id)
    except ContratacionError as err:
        raise _error(err)
    return {**_empresa(e), "usuario": _usuario(u),
            "evaluaciones": [await _datos_evaluacion(db, ev.id) for ev in evaluaciones]}


@router.post("/empresas/{empresa_id}/evaluaciones")
async def asociar_evaluaciones(empresa_id: int, payload: AsociarRequest,
                               actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    try:
        migradas = await EmpresasClienteUseCase(db).asociar_evaluaciones(actor, empresa_id, payload.solicitudes_ids)
    except (ContratacionError, MigracionError) as err:
        raise _error(err)
    return {"empresa_id": empresa_id, "evaluaciones_migradas": _migradas(migradas)}


@router.post("/empresas/{empresa_id}/usuario/activacion")
async def reenviar_activacion(empresa_id: int, actor: Actor = Depends(solo_admin),
                              db: AsyncSession = Depends(get_db)):
    try:
        r = await EmpresasClienteUseCase(db).reenviar_activacion(actor, empresa_id)
    except ContratacionError as err:
        raise _error(err)
    return {"empresa_id": empresa_id, "activacion": _correo(r)}


# ------------------------------------------------------------------ bitácora (HU-09 base)
@router.get("/bitacora")
async def bitacora(
    entidad: str | None = Query(None, max_length=40),
    entidad_id: int | None = Query(None),
    accion: str | None = Query(None, max_length=60),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    filas, total = await BitacoraRepository(db).listar(entidad=entidad, entidad_id=entidad_id, accion=accion,
                                                       page=page, size=size)
    return {
        "items": [{"id": f.id, "fecha": f.fecha, "actor_rol": f.actor_rol, "actor_id": f.actor_id,
                   "accion": f.accion, "entidad": f.entidad, "entidad_id": f.entidad_id,
                   "resultado": f.resultado, "detalle": f.detalle} for f in filas],
        "total": total, "page": page, "size": size,
    }
