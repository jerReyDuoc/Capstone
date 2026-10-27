"""
HU-28: sesiones revocables de los usuarios con contraseña (admin_therion y cliente).

El token bearer sigue siendo stateless (HMAC, app/core/autenticacion.py), pero al iniciar
sesión se crea una fila en sesion_usuario y el token lleva su identificador (`sid`). En
cada petición obtener_actor() comprueba que esa sesión siga abierta, así:

  - "Cerrar sesión" invalida el token en el servidor al instante; no depende de que el
    navegador borre la cookie (una copia robada del token también deja de servir).
  - Restablecer la contraseña cierra TODAS las sesiones abiertas de esa cuenta.

Del sid solo se guarda el SHA-256: con un respaldo de la BD no se puede rearmar un token
(además haría falta AUTH_SECRET para firmarlo).

Ninguna función hace commit: van en la transacción de quien llama (login, logout,
restablecimiento), junto con su registro en la bitácora.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.autenticacion import Actor, emitir_token
from app.core.config import settings
from app.domain.models.sesion import ROLES_CON_CONTRASENA, SesionUsuario


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_sid(sid: str) -> str:
    return hashlib.sha256(sid.encode("ascii")).hexdigest()


async def abrir_sesion(db: AsyncSession, rol: str, actor_id: int,
                       ahora: datetime | None = None) -> tuple[str, SesionUsuario]:
    """Crea la sesión y devuelve (token firmado con su sid, fila). NO hace commit."""
    if rol not in ROLES_CON_CONTRASENA:
        raise ValueError(f"El rol {rol} no inicia sesión con contraseña.")
    ahora = ahora or _ahora()
    sid = secrets.token_urlsafe(24)  # 32 caracteres
    fila = SesionUsuario(
        sid_hash=hash_sid(sid), actor_rol=rol, actor_id=actor_id, fecha_inicio=ahora,
        fecha_expiracion=ahora + timedelta(minutes=settings.AUTH_TOKEN_TTL_MIN),
    )
    db.add(fila)
    await db.flush()
    return emitir_token(actor_id, rol, sid=sid), fila


async def _buscar(db: AsyncSession, actor: Actor) -> SesionUsuario | None:
    if not actor.sid:
        return None
    fila = await db.scalar(select(SesionUsuario).where(SesionUsuario.sid_hash == hash_sid(actor.sid)))
    # El sid debe ser de ESTE usuario (defensa en profundidad: el token ya va firmado)
    if fila is None or fila.actor_rol != actor.rol or fila.actor_id != actor.id:
        return None
    return fila


async def sesion_vigente(db: AsyncSession, actor: Actor) -> bool:
    fila = await _buscar(db, actor)
    return fila is not None and fila.vigente(_ahora())


async def cerrar_sesion(db: AsyncSession, actor: Actor, motivo: str,
                        ahora: datetime | None = None) -> SesionUsuario | None:
    """Cierra la sesión del token. Devuelve la fila (None si el token no traía sesión). NO hace commit."""
    fila = await _buscar(db, actor)
    if fila is None or fila.fecha_cierre is not None:
        return fila
    fila.fecha_cierre = ahora or _ahora()
    fila.motivo_cierre = motivo
    return fila


async def cerrar_todas(db: AsyncSession, rol: str, actor_id: int, motivo: str,
                       ahora: datetime | None = None) -> int:
    """Cierra todas las sesiones abiertas de una cuenta. Devuelve cuántas cerró. NO hace commit."""
    ahora = ahora or _ahora()
    resultado = await db.execute(
        update(SesionUsuario)
        .where(SesionUsuario.actor_rol == rol, SesionUsuario.actor_id == actor_id,
               SesionUsuario.fecha_cierre.is_(None), SesionUsuario.fecha_expiracion > ahora)
        .values(fecha_cierre=ahora, motivo_cierre=motivo)
        .execution_options(synchronize_session=False)
    )
    return int(resultado.rowcount or 0)
