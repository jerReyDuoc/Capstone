"""
HU-19: encuesta pública desde la landing (sin invitación ni registro).

  POST  /api/encuesta-publica/iniciar   aviso legal + rubro + CAPTCHA -> evaluación, clave y token
  PATCH /api/encuesta-publica/email     (encuestado) email OPCIONAL para retomar/recibir el informe
  GET   /api/encuesta-publica/limites   (encuestado) evidencias y validaciones con IA restantes hoy
  GET   /api/encuesta-publica/aviso-legal  versión vigente del aviso legal (HU-04)

Retomar más tarde: POST /api/auth/encuestado {evaluacion_id, clave} (ya existía).

El único cliente legítimo de /iniciar es el BFF de Next.js: entrega el token en una
cookie httpOnly y nunca al JavaScript del navegador. Con BFF_SHARED_SECRET configurado
(obligatorio en producción), una llamada directa recibe 403.
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.iniciar_encuesta_publica import (
    EncuestaPublicaError,
    IniciarEncuestaPublicaUseCase,
)
from app.application.use_cases.limites_encuesta import LimitesEncuesta, ventana_diaria
from app.core.autenticacion import Actor, Rol, requerir_rol
from app.core.cliente import huella, ip_cliente, viene_del_bff
from app.core.config import settings
from app.core.database import get_db
from app.domain.models.evaluacion import Evaluacion
from app.domain.models.usuario_temporal import UsuarioTemporal
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador
from app.infrastructure.security.captcha import verificar_captcha

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/encuesta-publica", tags=["encuesta pública (HU-19)"])

_SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s.]{2,}$")


class AvisoLegalAceptado(BaseModel):
    version: str = Field(..., max_length=20)
    aceptado: bool


class IniciarEncuestaRequest(BaseModel):
    rubro_id: int = Field(..., ge=1)
    aviso_legal: AvisoLegalAceptado
    captcha_token: str = Field("", max_length=2048)


class EmailOpcionalRequest(BaseModel):
    # null = borrar el email registrado
    email: str | None = Field(None, max_length=100)


def _error(status: int, codigo: str, mensaje: str, reintentar_en_s: int | None = None, **extra) -> HTTPException:
    detail = {"codigo": codigo, "mensaje": mensaje, **extra}
    headers = dict(_SIN_CACHE)
    if reintentar_en_s:
        detail["reintentar_en_s"] = reintentar_en_s
        headers["Retry-After"] = str(reintentar_en_s)
    return HTTPException(status_code=status, detail=detail, headers=headers)


def _limitador_caido() -> HTTPException:
    return _error(503, "LIMITADOR_NO_DISPONIBLE",
                  "No podemos iniciar evaluaciones en este momento. Intenta en unos minutos.", 60)


@router.get("/aviso-legal")
async def aviso_legal_vigente():
    return {"version": settings.AVISO_LEGAL_VERSION}


@router.post(
    "/iniciar",
    status_code=201,
    responses={
        403: {"description": "CAPTCHA_INVALIDO u ORIGEN_NO_PERMITIDO"},
        409: {"description": "AVISO_DESACTUALIZADO"},
        422: {"description": "AVISO_NO_ACEPTADO o RUBRO_INVALIDO"},
        429: {"description": "DEMASIADOS_INTENTOS o LIMITE_EVALUACIONES (con Retry-After)"},
    },
)
async def iniciar_encuesta(
    payload: IniciarEncuestaRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    """
    Crea el usuario temporal anónimo y su evaluación. Devuelve la **clave de acceso
    una sola vez** (para retomar) y el token del encuestado.
    """
    if settings.BFF_SHARED_SECRET and not viene_del_bff(request):
        raise _error(403, "ORIGEN_NO_PERMITIDO", "Inicia la evaluación desde el sitio web.")
    if not payload.aviso_legal.aceptado:
        raise _error(422, "AVISO_NO_ACEPTADO", "Debes aceptar el aviso legal para comenzar.")

    ip = ip_cliente(request)
    id_ip = huella(ip)
    try:
        # 1. Intentos (también los fallidos): frena el abuso del CAPTCHA y del endpoint
        intentos = await limitador.consumir(f"ini:int:{id_ip}", settings.ENCUESTA_INTENTOS_IP_10MIN, 600)
        if not intentos.permitido:
            raise _error(429, "DEMASIADOS_INTENTOS",
                         "Hiciste muchos intentos seguidos. Espera unos minutos y vuelve a intentarlo.",
                         intentos.reintentar_en_s)

        # 2. CAPTCHA validado en el servidor (token de un solo uso)
        captcha = await verificar_captcha(payload.captcha_token, ip)
        if not captcha.valido:
            logger.info("CAPTCHA rechazado (%s)", captcha.motivo)
            raise _error(403, "CAPTCHA_INVALIDO", "No pudimos verificar que eres una persona. Inténtalo de nuevo.")

        # 3. Evaluaciones creadas por IP y día
        fecha, ventana, _ = ventana_diaria()
        clave_dia = f"ini:dia:{id_ip}:{fecha}"
        creadas = await limitador.consumir(clave_dia, settings.ENCUESTA_EVALUACIONES_IP_DIA, ventana)
        if not creadas.permitido:
            raise _error(429, "LIMITE_EVALUACIONES",
                         "Se alcanzó el máximo de evaluaciones nuevas por hoy desde tu red. "
                         "Si ya empezaste una, puedes retomarla con tu clave.",
                         creadas.reintentar_en_s)
    except LimitadorNoDisponibleError:
        raise _limitador_caido()

    try:
        iniciada = await IniciarEncuestaPublicaUseCase(db).execute(
            payload.rubro_id, payload.aviso_legal.version
        )
    except EncuestaPublicaError as e:
        await limitador.devolver(clave_dia)
        raise _error(e.status_code, e.codigo, str(e), version_vigente=settings.AVISO_LEGAL_VERSION)
    except Exception:
        await limitador.devolver(clave_dia)
        raise

    return JSONResponse(
        status_code=201,
        headers=_SIN_CACHE,
        content={
            "evaluacion_id": iniciada.evaluacion_id,
            "clave_acceso": iniciada.clave_acceso,
            "access_token": iniciada.access_token,
            "token_type": "bearer",
            "expira_en": iniciada.expira_en,
        },
    )


@router.patch("/email", status_code=204)
async def registrar_email(
    payload: EmailOpcionalRequest,
    actor: Actor = Depends(requerir_rol(Rol.ENCUESTADO)),
    db: AsyncSession = Depends(get_db),
):
    """Email OPCIONAL del encuestado (recibir el informe / retomar). Nunca bloquea el flujo."""
    email = (payload.email or "").strip().lower() or None
    if email is not None and not _EMAIL.match(email):
        raise _error(422, "EMAIL_INVALIDO", "Revisa el formato del correo (ejemplo: nombre@empresa.cl).")

    evaluacion = await db.get(Evaluacion, actor.id)
    usuario = await db.get(UsuarioTemporal, evaluacion.usuario_temporal_id) if evaluacion else None
    if usuario is None:
        raise _error(404, "EVALUACION_NO_ENCONTRADA", "Evaluación no encontrada")
    usuario.email = email
    await db.commit()
    return Response(status_code=204, headers=_SIN_CACHE)


@router.get("/limites")
async def limites_encuesta(
    actor: Actor = Depends(requerir_rol(Rol.ENCUESTADO)),
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    """Evidencias y validaciones con IA restantes hoy para la evaluación del encuestado."""
    try:
        return await LimitesEncuesta(db, limitador).estado(actor.id)
    except LimitadorNoDisponibleError:
        raise _error(503, "LIMITADOR_NO_DISPONIBLE", "No pudimos consultar los límites. Intenta en unos minutos.", 60)
