"""
HU-31 · "Contratar la plataforma" desde los resultados (sin cuenta).

  GET  /api/contratacion/consentimiento                  textos y versiones de los DOS consentimientos
  POST /api/contratacion/solicitudes                     el encuestado/referente pide que lo contacten
  GET  /api/contratacion/evaluaciones/{id}/solicitud     estado de su solicitud (para no pedir dos veces)

El formulario lleva nombre, cargo, empresa, correo y teléfono opcional (criterio 1) y dos
consentimientos separados con su versión (criterio 2). Al registrarse, la solicitud llega
a la bandeja del admin como 'nueva' y se avisa por correo a Therion Labs (criterio 3).

Límite contra abuso, el MISMO de la encuesta pública (HU-19, /api/encuesta-publica/iniciar):
  1. intentos por IP en 10 minutos (también los fallidos)  ENCUESTA_INTENTOS_IP_10MIN
  2. CAPTCHA (Turnstile) validado en el servidor            acción 'solicitar_contratacion'
  3. solicitudes por IP y día                               CONTRATACION_SOLICITUDES_IP_DIA
Con BFF_SHARED_SECRET configurado solo se acepta desde el BFF (IP real del visitante).

La gestión (cambiar estado, alta de empresa y migración) está en /api/admin (admin_clientes.py).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases import consentimientos_contratacion
from app.application.use_cases.aviso_contratacion import avisar_nueva_solicitud
from app.application.use_cases.contratacion_empresa import (
    ConsentimientoDado, ContratacionError, SolicitudesContratacionUseCase,
)
from app.application.use_cases.limites_encuesta import ventana_diaria
from app.core.autenticacion import Actor, Rol, requerir_rol
from app.core.cliente import huella, ip_cliente, viene_del_bff
from app.core.config import settings
from app.core.database import get_db
from app.domain.models.solicitud_contratacion import SolicitudContratacion
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador
from app.infrastructure.security.captcha import ACCION_CONTRATACION, verificar_captcha

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contratacion", tags=["contratación (HU-31)"])

solo_temporal = requerir_rol(Rol.ENCUESTADO, Rol.REFERENTE)

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _http(status: int, codigo: str, mensaje: str, reintentar_en_s: int | None = None, **extra) -> HTTPException:
    detail = {"codigo": codigo, "mensaje": mensaje, **extra}
    headers = dict(_SIN_CACHE)
    if reintentar_en_s:
        detail["reintentar_en_s"] = reintentar_en_s
        headers["Retry-After"] = str(reintentar_en_s)
    return HTTPException(status_code=status, detail=detail, headers=headers)


def _error(e: ContratacionError) -> HTTPException:
    return _http(e.status_code, e.codigo, str(e), **e.extra)


class ConsentimientoRequest(BaseModel):
    version: str = Field(..., max_length=20)
    aceptado: bool


class CrearSolicitudRequest(BaseModel):
    evaluacion_id: int = Field(..., ge=1)
    nombre: str = Field(..., max_length=200)
    cargo: str = Field(..., max_length=200)
    empresa: str = Field(..., max_length=200)
    email: str = Field(..., max_length=200)
    telefono: str | None = Field(None, max_length=40)
    consentimiento_contacto: ConsentimientoRequest
    consentimiento_migracion: ConsentimientoRequest
    captcha_token: str = Field("", max_length=2048)


def _publica(s: SolicitudContratacion) -> dict:
    """Lo que ve el propio encuestado: el estado, nunca notas ni datos de gestión."""
    return {
        "id": s.id,
        "evaluacion_id": s.evaluacion_id,
        # 'migrada' es técnico (HU-27): para la persona su solicitud está contratada
        "estado": "contratada" if s.estado == "migrada" else s.estado,
        "autoriza_migracion": s.autoriza_migracion,
        "fecha_creacion": s.fecha_creacion,
    }


@router.get("/consentimiento")
async def consentimiento():
    """Los dos textos vigentes. El formulario los muestra tal cual y devuelve su versión."""
    textos = consentimientos_contratacion.vigentes()
    return {
        "contacto": textos[consentimientos_contratacion.CONTACTO].como_dict(),
        "migracion": textos[consentimientos_contratacion.MIGRACION].como_dict(),
    }


@router.post(
    "/solicitudes",
    status_code=201,
    responses={
        403: {"description": "CAPTCHA_INVALIDO u ORIGEN_NO_PERMITIDO"},
        409: {"description": "SOLICITUD_EXISTENTE, EVALUACION_NO_COMPLETADA o CONSENTIMIENTO_DESACTUALIZADO"},
        422: {"description": "CONSENTIMIENTO_REQUERIDO, DATOS_INVALIDOS o EMAIL_INVALIDO"},
        429: {"description": "DEMASIADOS_INTENTOS o LIMITE_SOLICITUDES (con Retry-After)"},
    },
)
async def crear_solicitud(
    payload: CrearSolicitudRequest,
    request: Request,
    actor: Actor = Depends(solo_temporal),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    """El encuestado pide que Therion Labs lo contacte para contratar la plataforma."""
    if settings.BFF_SHARED_SECRET and not viene_del_bff(request):
        raise _http(403, "ORIGEN_NO_PERMITIDO", "Envía la solicitud desde el sitio web.")

    ip = ip_cliente(request)
    id_ip = huella(ip)
    try:
        # 1. Intentos (también los fallidos), igual que /encuesta-publica/iniciar
        intentos = await limitador.consumir(f"ctr:int:{id_ip}", settings.ENCUESTA_INTENTOS_IP_10MIN, 600)
        if not intentos.permitido:
            raise _http(429, "DEMASIADOS_INTENTOS",
                        "Hiciste muchos intentos seguidos. Espera unos minutos y vuelve a intentarlo.",
                        intentos.reintentar_en_s)

        # 2. CAPTCHA en el servidor (token de un solo uso, acción propia de este formulario)
        captcha = await verificar_captcha(payload.captcha_token, ip, ACCION_CONTRATACION)
        if not captcha.valido:
            logger.info("CAPTCHA de contratación rechazado (%s)", captcha.motivo)
            raise _http(403, "CAPTCHA_INVALIDO", "No pudimos verificar que eres una persona. Inténtalo de nuevo.")

        # 3. Solicitudes por IP y día
        fecha, ventana, _ = ventana_diaria()
        clave_dia = f"ctr:dia:{id_ip}:{fecha}"
        creadas = await limitador.consumir(clave_dia, settings.contratacion_solicitudes_ip_dia, ventana)
        if not creadas.permitido:
            raise _http(429, "LIMITE_SOLICITUDES",
                        "Se alcanzó el máximo de solicitudes por hoy desde tu red. Inténtalo mañana o "
                        "escríbenos directamente.", creadas.reintentar_en_s)
    except LimitadorNoDisponibleError:
        raise _http(503, "LIMITADOR_NO_DISPONIBLE",
                    "No podemos recibir solicitudes en este momento. Intenta en unos minutos.", 60)

    try:
        s = await SolicitudesContratacionUseCase(db).crear(
            actor, evaluacion_id=payload.evaluacion_id, nombre=payload.nombre, cargo=payload.cargo,
            empresa=payload.empresa, email=payload.email, telefono=payload.telefono,
            consentimiento_contacto=ConsentimientoDado(payload.consentimiento_contacto.aceptado,
                                                       payload.consentimiento_contacto.version),
            consentimiento_migracion=ConsentimientoDado(payload.consentimiento_migracion.aceptado,
                                                        payload.consentimiento_migracion.version),
        )
    except ContratacionError as e:
        await limitador.devolver(clave_dia)  # un formulario rechazado no gasta el cupo del día
        raise _error(e)
    except Exception:
        await limitador.devolver(clave_dia)
        raise

    # Criterio 3: aviso a Therion DESPUÉS del commit; si falla, la solicitud ya está en la bandeja
    try:
        await avisar_nueva_solicitud(db, s)
    except Exception:  # noqa: BLE001  (el aviso es interno: nunca debe tumbar la respuesta)
        logger.exception("Falló el aviso de la solicitud de contratación %s", s.id)
        await db.rollback()
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
        raise _http(404, "SIN_SOLICITUD", "Aún no solicitas la contratación.")
    return _publica(s)
