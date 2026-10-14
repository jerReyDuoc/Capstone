from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.iniciar_sesion import CredencialesInvalidasError, IniciarSesionUseCase
from app.core.autenticacion import Actor, obtener_actor
from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginAdminRequest(BaseModel):
    email: str
    password: str


class AccesoTitularRequest(BaseModel):
    usuario_temporal_id: int
    email: str


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


@router.get("/me")
async def quien_soy(actor: Actor = Depends(obtener_actor)):
    """Identidad del token actual (útil para el frontend)."""
    return {"usuario_id": actor.id, "rol": actor.rol}
