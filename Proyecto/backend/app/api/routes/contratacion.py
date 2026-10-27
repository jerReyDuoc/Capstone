"""
Solicitud de contratación del servicio pagado (BASE MÍNIMA de HU-31, creada para HU-27).

  GET  /api/contratacion/consentimiento                       versión y texto de la autorización
  POST /api/contratacion/solicitudes                          el encuestado/referente pide contratar
  GET  /api/contratacion/evaluaciones/{id}/solicitud          estado de su solicitud

Lo usa el usuario temporal al final de su evaluación. La gestión (marcar contratada,
alta de empresa y migración) está en /api/admin (admin_clientes.py).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.contratacion_empresa import ContratacionError, SolicitudesContratacionUseCase
from app.core.autenticacion import Actor, Rol, requerir_rol
from app.core.config import settings
from app.core.database import get_db
from app.domain.models.solicitud_contratacion import SolicitudContratacion

router = APIRouter(prefix="/api/contratacion", tags=["contratación (HU-31 base / HU-27)"])

solo_temporal = requerir_rol(Rol.ENCUESTADO, Rol.REFERENTE)

# Texto PROVISORIO: el PO debe aprobar el definitivo (pendiente "textos de consentimiento").
# Al cambiarlo, sube CONSENTIMIENTO_CONTRATACION_VERSION.
TEXTO_CONSENTIMIENTO = (
    "Autorizo a Therion Labs a traspasar a mi empresa, si contrata el servicio, esta evaluación "
    "con sus respuestas, evidencias, resultados, plan formativo e informes. Al traspasarla, mi "
    "acceso temporal y su clave dejan de funcionar y mis datos de contacto de esta solicitud se "
    "eliminan; el acceso continuará con el usuario definitivo que se cree para la empresa."
)


def _error(e: ContratacionError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail={"codigo": e.codigo, "mensaje": str(e), **e.extra})


class CrearSolicitudRequest(BaseModel):
    evaluacion_id: int = Field(..., ge=1)
    nombre: str = Field(..., max_length=200)
    email: str = Field(..., max_length=200)
    telefono: str | None = Field(None, max_length=40)
    razon_social: str | None = Field(None, max_length=200)
    autoriza_migracion: bool
    consentimiento_version: str | None = Field(None, max_length=20)


def _publica(s: SolicitudContratacion) -> dict:
    """Lo que ve el propio usuario temporal (sin datos de otros)."""
    return {
        "id": s.id,
        "evaluacion_id": s.evaluacion_id,
        "estado": s.estado,
        "autoriza_migracion": s.autoriza_migracion,
        "fecha_creacion": s.fecha_creacion,
    }


@router.get("/consentimiento")
async def consentimiento():
    return {"version": settings.CONSENTIMIENTO_CONTRATACION_VERSION, "texto": TEXTO_CONSENTIMIENTO}


@router.post("/solicitudes", status_code=201)
async def crear_solicitud(
    payload: CrearSolicitudRequest,
    actor: Actor = Depends(solo_temporal),
    db: AsyncSession = Depends(get_db),
):
    """El usuario temporal pide contratar y (opcionalmente) autoriza traspasar su evaluación."""
    try:
        s = await SolicitudesContratacionUseCase(db).crear(
            actor, evaluacion_id=payload.evaluacion_id, nombre=payload.nombre, email=payload.email,
            telefono=payload.telefono, razon_social=payload.razon_social,
            autoriza_migracion=payload.autoriza_migracion, consentimiento_version=payload.consentimiento_version,
        )
    except ContratacionError as e:
        raise _error(e)
    return _publica(s)


@router.get("/evaluaciones/{evaluacion_id}/solicitud")
async def mi_solicitud(
    evaluacion_id: int,
    actor: Actor = Depends(solo_temporal),
    db: AsyncSession = Depends(get_db),
):
    uc = SolicitudesContratacionUseCase(db)
    try:
        await uc.evaluacion_del_actor(actor, evaluacion_id)
    except ContratacionError as e:
        raise _error(e)
    s = await db.scalar(select(SolicitudContratacion).where(SolicitudContratacion.evaluacion_id == evaluacion_id))
    if s is None:
        raise HTTPException(status_code=404, detail={"codigo": "SIN_SOLICITUD",
                                                     "mensaje": "Aún no solicitas la contratación."})
    return _publica(s)
