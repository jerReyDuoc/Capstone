from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.clave_acceso_encuestado import (
    EvaluacionNoEncontradaError, generar_clave_acceso,
)
from app.application.use_cases.iniciar_sesion import CredencialesInvalidasError, IniciarSesionUseCase
from app.core.autenticacion import Actor, Rol, obtener_actor, requerir_rol
from app.core.config import settings
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


@router.post("/encuestado")
async def acceso_encuestado(payload: AccesoEncuestadoRequest, db: AsyncSession = Depends(get_db)):
    """
    Acceso del encuestado anónimo de la encuesta pública (rol encuestado) con el id de
    su evaluación y la clave de acceso que recibió al iniciarla. Con el token puede
    registrar y consultar sus solicitudes ARCOP.
    """
    _exigir_secreto()
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
