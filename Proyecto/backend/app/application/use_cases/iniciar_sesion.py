"""
Emisión de tokens de acceso (ver app/core/autenticacion.py).

  - Admin:   email + contraseña contra usuarios_admin (hash PBKDF2).
  - Titular: usuario_temporal_id + email de la invitación; la invitación no debe
             estar expirada ni el usuario anonimizado.

Los errores son deliberadamente genéricos ("credenciales inválidas") para no
revelar si un email o id existe.
"""
import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import (
    Rol, emitir_token, verificar_password, verificar_password_senuelo,
)
from app.core.config import settings
from app.domain.models.usuario_admin import UsuarioAdmin
from app.domain.models.usuario_temporal import UsuarioTemporal

logger = logging.getLogger("seguridad")


class CredencialesInvalidasError(Exception):
    pass


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def _respuesta(usuario_id: int, rol: Rol) -> dict:
    return {
        "access_token": emitir_token(usuario_id, rol.value),
        "token_type": "bearer",
        "rol": rol.value,
        "usuario_id": usuario_id,
        "expira_en_min": settings.AUTH_TOKEN_TTL_MIN,
    }


class IniciarSesionUseCase:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def admin(self, email: str, password: str) -> dict:
        email = _normalizar_email(email)
        result = await self.db.execute(
            select(UsuarioAdmin).where(func.lower(UsuarioAdmin.email) == email)
        )
        admin = result.scalar_one_or_none()
        if admin is None:
            verificar_password_senuelo(password or "")
            ok = False
        else:
            ok = verificar_password(password or "", admin.password_hash) and admin.activo
        if not ok:
            logger.warning("Login de administrador fallido")
            raise CredencialesInvalidasError("Credenciales inválidas.")
        admin.ultimo_acceso = _ahora()
        await self.db.commit()
        return _respuesta(admin.id, Rol.ADMIN_THERION)

    async def titular(self, usuario_temporal_id: int, email: str) -> dict:
        usuario = await self.db.get(UsuarioTemporal, usuario_temporal_id)
        valido = (
            usuario is not None
            and usuario.fecha_anonimizacion is None
            and usuario.email is not None
            and usuario.email.strip().lower() == _normalizar_email(email)
            and (usuario.fecha_expiracion is None or usuario.fecha_expiracion >= date.today())
        )
        if not valido:
            raise CredencialesInvalidasError(
                "Credenciales inválidas o invitación expirada."
            )
        return _respuesta(usuario.id, Rol.REFERENTE)
