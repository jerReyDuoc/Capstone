from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.clave_acceso_encuestado import (
    EvaluacionNoEncontradaError, generar_clave_acceso,
)
from app.application.use_cases.iniciar_sesion import CredencialesInvalidasError, IniciarSesionUseCase
from app.core.autenticacion import Actor, Rol, obtener_actor, requerir_rol
from app.core.cliente import huella, ip_cliente
from app.core.config import settings
from app.infrastructure.cache.limitador import Limitador, LimitadorNoDisponibleError, obtener_limitador
from app.core.database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginAdminRequest(BaseModel):
    email: str
    password: str


class AccesoTitularRequest(BaseModel):
    usuario_temporal_id: int
    email: str


class AccesoEncuestadoRequest(BaseModel):
    evaluacion_id: int
    clave: str


class GenerarClaveRequest(BaseModel):
    evaluacion_id: int


def _exigir_secreto():
    if not settings.AUTH_SECRET:
        raise HTTPException(
            status_code=503,
            detail={"codigo": "AUTH_NO_CONFIGURADA", "mensaje": "AUTH_SECRET no está configurado en el servidor."},
        )


@router.post("/login")
async def login_admin(payload: LoginAdminRequest, db: AsyncSession = Depends(get_db)):
    """Login del administrador (rol admin_therion). Devuelve el token bearer."""
    _exigir_secreto()
    try:
        return await IniciarSesionUseCase(db).admin(payload.email, payload.password)
    except CredencialesInvalidasError as e:
        raise HTTPException(status_code=401, detail={"codigo": "CREDENCIALES_INVALIDAS", "mensaje": str(e)})


@router.post("/titular")
async def acceso_titular(payload: AccesoTitularRequest, db: AsyncSession = Depends(get_db)):
    """
    Acceso del usuario temporal (rol referente) con los datos de su invitación.
    Con el token puede registrar y consultar sus solicitudes ARCOP.
    """
    _exigir_secreto()
    try:
        return await IniciarSesionUseCase(db).titular(payload.usuario_temporal_id, payload.email)
    except CredencialesInvalidasError as e:
        raise HTTPException(status_code=401, detail={"codigo": "CREDENCIALES_INVALIDAS", "mensaje": str(e)})


# HU-19: límites de intentos para retomar con clave (fuerza bruta). La clave tiene ~60
# bits de azar y PBKDF2 lento; esto además corta los intentos masivos por IP y por evaluación.
_RETOMAR_IP_10MIN = 20
_RETOMAR_EVALUACION_15MIN = 10


@router.post("/encuestado")
async def acceso_encuestado(
    payload: AccesoEncuestadoRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limitador: Limitador = Depends(obtener_limitador),
):
    """
    Acceso del encuestado anónimo de la encuesta pública (rol encuestado) con el id de
    su evaluación y la clave de acceso que recibió al iniciarla. Con el token retoma su
    evaluación (HU-19) y puede registrar y consultar sus solicitudes ARCOP.
    """
    _exigir_secreto()
    try:
        por_ip = await limitador.consumir(f"ret:ip:{huella(ip_cliente(request))}", _RETOMAR_IP_10MIN, 600)
        por_ev = await limitador.consumir(f"ret:ev:{payload.evaluacion_id}", _RETOMAR_EVALUACION_15MIN, 900)
    except LimitadorNoDisponibleError:
        raise HTTPException(status_code=503, headers={"Retry-After": "60"}, detail={
            "codigo": "LIMITADOR_NO_DISPONIBLE", "mensaje": "Intenta de nuevo en unos minutos."})
    if not (por_ip.permitido and por_ev.permitido):
        espera = max(por_ip.reintentar_en_s if not por_ip.permitido else 0,
                     por_ev.reintentar_en_s if not por_ev.permitido else 0)
        raise HTTPException(status_code=429, headers={"Retry-After": str(espera)}, detail={
            "codigo": "DEMASIADOS_INTENTOS", "reintentar_en_s": espera,
            "mensaje": "Demasiados intentos. Espera unos minutos antes de volver a probar tu clave."})
    try:
        return await IniciarSesionUseCase(db).encuestado(payload.evaluacion_id, payload.clave)
    except CredencialesInvalidasError as e:
        raise HTTPException(status_code=401, detail={"codigo": "CREDENCIALES_INVALIDAS", "mensaje": str(e)})


@router.post("/encuestado/clave", status_code=201)
async def generar_clave_encuestado(
    payload: GenerarClaveRequest,
    actor: Actor = Depends(requerir_rol(Rol.ADMIN_THERION)),
    db: AsyncSession = Depends(get_db),
):
    """
    admin_therion genera (o regenera) la clave de acceso de una evaluación.
    La clave se muestra UNA sola vez; la anterior deja de servir.
    Uso: soporte y pruebas mientras la encuesta pública (HU-19) no la entregue sola.
    """
    try:
        clave = await generar_clave_acceso(db, payload.evaluacion_id)
    except EvaluacionNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"evaluacion_id": payload.evaluacion_id, "clave": clave}


@router.get("/me")
async def quien_soy(actor: Actor = Depends(obtener_actor)):
    """Identidad del token actual (útil para el frontend)."""
    return {"usuario_id": actor.id, "rol": actor.rol}
