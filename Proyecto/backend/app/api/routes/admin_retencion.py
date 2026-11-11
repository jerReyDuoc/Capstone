"""
HU-25 · Retención de usuarios temporales vencidos (solo admin_therion: Oficial de Privacidad).

    GET   /api/admin/retencion                    plazo vigente, pendientes, próxima y última ejecución
    PATCH /api/admin/retencion                    {modo: entorno|plazo|desactivada, plazo_titular_dias}
    GET   /api/admin/retencion/vista-previa?dias=N  cuántos titulares anonimizaría ese plazo HOY
    POST  /api/admin/retencion/simulacion         corre la retención SIN cambiar nada (queda en el log)
    POST  /api/admin/retencion/ejecuciones        {confirmar: true} encola una ejecución real en el worker
    GET   /api/admin/retencion/ejecuciones        historial de ejecuciones (desde el audit_log)

Criterio 1: el plazo se cambia aquí sin reiniciar nada (lo lee cada ejecución). Criterio 2:
la tarea es app/worker/tasks.py:aplicar_retencion_task (cron diario) y reutiliza la
anonimización de ARCOP. Criterio 3: cada ejecución y cada cambio de plazo queda en el
audit_log; el historial de esta pantalla se lee de ahí, no de una tabla aparte.

La vista previa no es una ejecución y no se registra (se pide al escribir el plazo).
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.aplicar_retencion import ORIGEN_MANUAL, AplicarRetencionUseCase
from app.application.use_cases.configurar_retencion import (
    PlazoTitular,
    RetencionError,
    actualizar_plazo,
    plazo_titular_vigente,
    proxima_ejecucion,
    ahora_utc,
)
from app.core.alcance import solo_admin
from app.core.autenticacion import Actor
from app.core.config import settings
from app.core.database import get_db
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.repositories.bitacora_repository import Accion, BitacoraRepository

router = APIRouter(prefix="/api/admin/retencion", tags=["admin · retención (HU-25)"])

JOB_MANUAL = "retencion-manual"


class CambioRetencion(BaseModel):
    modo: str = Field(..., max_length=20)
    plazo_titular_dias: int | None = None


class PedidoEjecucion(BaseModel):
    confirmar: bool = False


def _error(e: RetencionError) -> HTTPException:
    return HTTPException(e.status, {"codigo": e.codigo, "mensaje": e.mensaje})


def _en_curso(p: PlazoTitular):
    """La marca solo cuenta si no está abandonada (worker caído)."""
    if p.ejecucion_desde is None:
        return None
    if p.ejecucion_desde < ahora_utc() - timedelta(minutes=settings.RETENCION_BLOQUEO_MAX_MIN):
        return None
    return p.ejecucion_desde


async def _pendientes(db: AsyncSession, dias: int | None) -> dict | None:
    if dias is None:
        return None
    r = await AplicarRetencionUseCase(
        db, plazos={"titulares": dias, "arcop": None, "eventos": None},
    ).execute(aplicar=False, registrar=False)
    return {"titulares": r.titulares, "omitidos_por_arcop_abierta": r.titulares_omitidos_por_arcop_abierta,
            "fecha_corte": (date.today() - timedelta(days=dias)).isoformat()}


def _fila(f) -> dict:
    return {"id": f.id, "fecha": f.fecha, "actor_rol": f.actor_rol, "actor_id": f.actor_id,
            "resultado": f.resultado, "detalle": f.detalle}


async def _estado(db: AsyncSession) -> dict:
    p = await plazo_titular_vigente(db)
    sin_vencimiento = (await db.execute(
        select(func.count()).select_from(UsuarioTemporal)
        .where(UsuarioTemporal.fecha_anonimizacion.is_(None), UsuarioTemporal.fecha_expiracion.is_(None))
    )).scalar_one()
    bitacora = BitacoraRepository(db)
    ultimas, _ = await bitacora.listar(accion=Accion.RETENCION_EJECUCION, page=1, size=1)
    cambios, _ = await bitacora.listar(accion=Accion.RETENCION_CONFIGURACION, page=1, size=5)
    return {
        **p.como_dict(),
        "valor_entorno_dias": settings.RETENCION_DATOS_TITULAR_DIAS,
        "limites": {"min_dias": settings.RETENCION_TITULAR_MIN_DIAS, "max_dias": settings.RETENCION_TITULAR_MAX_DIAS},
        "fecha_actualizacion": p.fecha_actualizacion,
        "ejecucion_en_curso_desde": _en_curso(p),
        "hora_utc": settings.RETENCION_HORA_UTC,
        "proxima_ejecucion": proxima_ejecucion(),
        "pendientes": await _pendientes(db, p.dias),
        "usuarios_sin_vencimiento": int(sin_vencimiento),
        "otras_reglas_dias": {"arcop_cerradas": settings.RETENCION_ARCOP_CERRADAS_DIAS,
                              "eventos_seguridad": settings.RETENCION_EVENTOS_SEGURIDAD_DIAS,
                              "tutor": settings.TUTOR_RETENCION_DIAS},
        "ultima_ejecucion": _fila(ultimas[0]) if ultimas else None,
        "cambios_recientes": [_fila(c) for c in cambios],
    }


@router.get("")
async def estado(_: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    return await _estado(db)


@router.patch("")
async def cambiar(cuerpo: CambioRetencion, actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    try:
        await actualizar_plazo(db, actor, modo=cuerpo.modo, dias=cuerpo.plazo_titular_dias)
    except RetencionError as e:
        raise _error(e) from None
    return await _estado(db)


@router.get("/vista-previa")
async def vista_previa(
    dias: int = Query(..., ge=1, le=100_000),
    _: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    if not settings.RETENCION_TITULAR_MIN_DIAS <= dias <= settings.RETENCION_TITULAR_MAX_DIAS:
        raise HTTPException(422, {"codigo": "PLAZO_INVALIDO", "mensaje": (
            f"El plazo debe estar entre {settings.RETENCION_TITULAR_MIN_DIAS} y "
            f"{settings.RETENCION_TITULAR_MAX_DIAS} días.")})
    return {"plazo_titular_dias": dias, "pendientes": await _pendientes(db, dias)}


@router.post("/simulacion")
async def simular(actor: Actor = Depends(solo_admin), db: AsyncSession = Depends(get_db)):
    """Corre todas las reglas en modo simulación con los plazos vigentes. Queda en el audit_log."""
    r = await AplicarRetencionUseCase(db, origen=ORIGEN_MANUAL, actor=actor).execute(aplicar=False)
    return r.como_dict()


@router.post("/ejecuciones", status_code=202)
async def ejecutar(cuerpo: PedidoEjecucion, request: Request, actor: Actor = Depends(solo_admin),
                   db: AsyncSession = Depends(get_db)):
    """
    Encola una ejecución REAL en el worker (puede tardar más que una petición HTTP). Anonimiza
    de forma irreversible: exige confirmar=true. Una sola a la vez (si ya hay una en cola o en
    curso, no se encola otra).
    """
    if not cuerpo.confirmar:
        raise HTTPException(422, {"codigo": "CONFIRMACION_REQUERIDA",
                                  "mensaje": "Confirma la ejecución: la anonimización no se puede deshacer."})
    p = await plazo_titular_vigente(db)
    if _en_curso(p):
        raise HTTPException(409, {"codigo": "EJECUCION_EN_CURSO",
                                  "mensaje": "Ya hay una ejecución de la retención en curso. Espera a que termine."})
    job = await request.app.state.arq.enqueue_job(
        "aplicar_retencion_task", "manual", actor.id, _job_id=JOB_MANUAL,
    )
    return {"encolada": True, "ya_en_cola": job is None,
            "mensaje": ("Ya había una ejecución en cola: se usará esa." if job is None else
                        "Ejecución encolada. En unos momentos aparecerá en el historial.")}


@router.get("/ejecuciones")
async def ejecuciones(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    filas, total = await BitacoraRepository(db).listar(accion=Accion.RETENCION_EJECUCION, page=page, size=size)
    return {"items": [_fila(f) for f in filas], "total": total, "page": page, "size": size}
