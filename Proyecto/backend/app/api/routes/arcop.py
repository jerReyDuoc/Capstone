"""
Solicitudes de derechos ARCOP del titular de datos personales
(Acceso, Rectificación, Supresión, Oposición, Portabilidad, Bloqueo).

Roles (app/core/autenticacion.py) y cómo obtener el token (app/api/routes/auth.py):
  referente      -> titular (POST /api/auth/titular): crea, consulta, cancela y aporta
                    información a SUS solicitudes.
  admin_therion  -> administrador (POST /api/auth/login): consulta todas, cambia estados
                    intermedios y registra la resolución. Una supresión resuelta
                    anonimiza los datos del titular.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor, Rol, obtener_actor, requerir_rol
from app.core.config import settings
from app.core.database import get_db
from app.application.schemas.arcop_schemas import (
    AportarInformacionARCOPRequest,
    CambiarEstadoARCOPRequest,
    CancelarSolicitudARCOPRequest,
    CrearSolicitudARCOPRequest,
    EventoSolicitudARCOPResponse,
    ResolverSolicitudARCOPRequest,
    SolicitudARCOPDetalleResponse,
    SolicitudARCOPResumenResponse,
)
from app.application.use_cases.gestionar_solicitud_arcop import (
    GestionarSolicitudARCOPUseCase,
    OperacionNoPermitidaError,
    SolicitudNoEncontradaError,
    TransicionInvalidaError,
    plazo_vencido,
)
from app.domain.models.solicitud_arcop import (
    TRANSICIONES_ARCOP,
    EstadoSolicitudARCOP,
    SolicitudARCOP,
    TipoSolicitudARCOP,
)
from app.infrastructure.repositories.anonimizacion_repository import AnonimizacionRepository
from app.infrastructure.repositories.solicitud_arcop_repository import SolicitudARCOPRepository
from app.infrastructure.storage.local_storage import LocalFileStorage

router = APIRouter(prefix="/api/arcop", tags=["arcop"])

solo_titular = requerir_rol(Rol.REFERENTE)
solo_admin = requerir_rol(Rol.ADMIN_THERION)


def _use_case(db: AsyncSession) -> GestionarSolicitudARCOPUseCase:
    return GestionarSolicitudARCOPUseCase(
        SolicitudARCOPRepository(db),
        anonimizacion_repo=AnonimizacionRepository(db),
        storage=LocalFileStorage(),
        plazo_respuesta_dias=settings.ARCOP_PLAZO_RESPUESTA_DIAS,
        plazo_informacion_dias=settings.ARCOP_PLAZO_INFORMACION_DIAS,
    )


async def _ejecutar(coro):
    """Traduce los errores del caso de uso al formato de errores de la API."""
    try:
        return await coro
    except SolicitudNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OperacionNoPermitidaError as e:
        raise HTTPException(status_code=403, detail={"codigo": "NO_AUTORIZADO", "mensaje": str(e)})
    except TransicionInvalidaError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "codigo": "TRANSICION_INVALIDA",
                "mensaje": str(e),
                "estado_actual": e.actual,
                "permitidas": sorted(TRANSICIONES_ARCOP.get(e.actual, set())),
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _resumen(s: SolicitudARCOP) -> SolicitudARCOPResumenResponse:
    return SolicitudARCOPResumenResponse(
        id_solicitud=s.id,
        tipo=s.tipo,
        estado=s.estado,
        usuario_temporal_id=s.usuario_temporal_id,
        fecha_creacion=s.fecha_creacion,
        fecha_actualizacion=s.fecha_actualizacion,
        fecha_cierre=s.fecha_cierre,
        fecha_limite_respuesta=s.fecha_limite_respuesta,
        fecha_limite_informacion=s.fecha_limite_informacion,
        plazo_vencido=plazo_vencido(s),
    )


def _detalle(s: SolicitudARCOP, actor: Actor) -> SolicitudARCOPDetalleResponse:
    return SolicitudARCOPDetalleResponse(
        **_resumen(s).model_dump(),
        descripcion=s.descripcion,
        respuesta=s.respuesta,
        transiciones_posibles=sorted(TRANSICIONES_ARCOP.get(s.estado, set())),
        historial=[
            EventoSolicitudARCOPResponse(
                id_evento=e.id,
                fecha=e.fecha,
                tipo_evento=e.tipo_evento,
                estado_anterior=e.estado_anterior,
                estado_nuevo=e.estado_nuevo,
                actor_rol=e.actor_rol,
                actor_id=e.actor_id if actor.es_admin else None,
                comentario=e.comentario,
            )
            for e in s.eventos
        ],
    )


@router.get("/catalogo")
async def catalogo_arcop():
    """Tipos de solicitud, estados y transiciones válidas (para formularios del frontend)."""
    return {
        "tipos": TipoSolicitudARCOP.valores(),
        "estados": EstadoSolicitudARCOP.valores(),
        "estados_finales": sorted(EstadoSolicitudARCOP.finales()),
        "transiciones": {k: sorted(v) for k, v in TRANSICIONES_ARCOP.items()},
        # None = plazo aún no definido por el equipo
        "plazo_respuesta_dias": settings.ARCOP_PLAZO_RESPUESTA_DIAS,
        "plazo_informacion_dias": settings.ARCOP_PLAZO_INFORMACION_DIAS,
    }


@router.post("/solicitudes", status_code=201, response_model=SolicitudARCOPDetalleResponse)
async def crear_solicitud(
    payload: CrearSolicitudARCOPRequest,
    actor: Actor = Depends(solo_titular),
    db: AsyncSession = Depends(get_db),
):
    """El titular registra una solicitud ARCOP. Queda en estado 'recibida'."""
    s = await _ejecutar(_use_case(db).crear(actor, payload.tipo, payload.descripcion))
    return _detalle(s, actor)


@router.get("/solicitudes")
async def listar_solicitudes(
    page: int = Query(1, ge=1, description="Número de página (empieza en 1)"),
    size: int = Query(20, ge=1, le=100, description="Registros por página (máx 100)"),
    estado: str | None = Query(None, description="Filtrar por estado"),
    tipo: str | None = Query(None, description="Filtrar por tipo de derecho"),
    usuario_temporal_id: int | None = Query(None, description="Solo admin_therion: filtrar por titular"),
    vencidas: bool = Query(False, description="Solo solicitudes abiertas con algún plazo vencido"),
    actor: Actor = Depends(obtener_actor),
    db: AsyncSession = Depends(get_db),
):
    """
    Titular: sus propias solicitudes (usuario_temporal_id se ignora).
    admin_therion: todas, con filtros.
    """
    items, total = await _ejecutar(
        _use_case(db).listar(actor, estado, tipo, usuario_temporal_id, page, size, solo_vencidas=vencidas)
    )
    return {
        "items": [_resumen(s) for s in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if size > 0 else 0,
    }


@router.get("/solicitudes/{solicitud_id}", response_model=SolicitudARCOPDetalleResponse)
async def obtener_solicitud(
    solicitud_id: int,
    actor: Actor = Depends(obtener_actor),
    db: AsyncSession = Depends(get_db),
):
    """Detalle con historial. Un titular solo ve las suyas (404 para las ajenas)."""
    s = await _ejecutar(_use_case(db).obtener(actor, solicitud_id))
    return _detalle(s, actor)


@router.patch("/solicitudes/{solicitud_id}/estado", response_model=SolicitudARCOPDetalleResponse)
async def cambiar_estado(
    solicitud_id: int,
    payload: CambiarEstadoARCOPRequest,
    actor: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    """admin_therion: en_revision | pendiente_informacion (comentario obligatorio) | en_proceso."""
    s = await _ejecutar(
        _use_case(db).cambiar_estado(actor, solicitud_id, payload.estado, payload.comentario)
    )
    return _detalle(s, actor)


@router.post("/solicitudes/{solicitud_id}/resolucion", response_model=SolicitudARCOPDetalleResponse)
async def resolver_solicitud(
    solicitud_id: int,
    payload: ResolverSolicitudARCOPRequest,
    actor: Actor = Depends(solo_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    admin_therion registra la respuesta: 'resuelta' (desde en_proceso) o 'rechazada'.
    Si es una SUPRESIÓN y queda 'resuelta', se anonimizan los datos del titular
    (irreversible) y su acceso queda revocado.
    """
    s = await _ejecutar(
        _use_case(db).resolver(actor, solicitud_id, payload.resultado, payload.respuesta)
    )
    return _detalle(s, actor)


@router.post("/solicitudes/{solicitud_id}/cancelacion", response_model=SolicitudARCOPDetalleResponse)
async def cancelar_solicitud(
    solicitud_id: int,
    payload: CancelarSolicitudARCOPRequest | None = None,
    actor: Actor = Depends(solo_titular),
    db: AsyncSession = Depends(get_db),
):
    """El titular desiste de su solicitud mientras no esté en proceso ni cerrada."""
    motivo = payload.motivo if payload else None
    s = await _ejecutar(_use_case(db).cancelar(actor, solicitud_id, motivo))
    return _detalle(s, actor)


@router.post("/solicitudes/{solicitud_id}/informacion", response_model=SolicitudARCOPDetalleResponse)
async def aportar_informacion(
    solicitud_id: int,
    payload: AportarInformacionARCOPRequest,
    actor: Actor = Depends(solo_titular),
    db: AsyncSession = Depends(get_db),
):
    """El titular responde a 'pendiente_informacion'; la solicitud vuelve a 'en_revision'."""
    s = await _ejecutar(_use_case(db).aportar_informacion(actor, solicitud_id, payload.informacion))
    return _detalle(s, actor)
