from datetime import datetime
from sqlalchemy import Integer, String, DateTime, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

# HU-28: roles con inicio de sesión por email y contraseña (los demás usan otros accesos)
ROLES_CON_CONTRASENA = ("admin_therion", "cliente")
_CHECK_ROL = "actor_rol IN ('admin_therion', 'cliente')"


class MotivoCierre:
    LOGOUT = "logout"                    # el usuario cerró sesión
    CAMBIO_CONTRASENA = "cambio_password"  # restableció su contraseña: se cierran todas


class SesionUsuario(Base):
    """
    HU-28: sesión de un administrador o de un usuario definitivo.

    El token bearer sigue siendo el HMAC de app/core/autenticacion.py, pero ahora lleva
    un identificador de sesión (`sid`, 24 bytes aleatorios). Aquí solo queda su SHA-256,
    y en cada petición se comprueba que la sesión exista, no haya vencido y no se haya
    cerrado. Así "Cerrar sesión" invalida el token en el servidor al instante (no solo
    borra la cookie del navegador) y restablecer la contraseña cierra todas las sesiones.

    No hay FK al usuario porque puede ser de dos tablas (usuarios_admin o
    usuario_definitivo); actor_rol dice cuál.
    """
    __tablename__ = "sesion_usuario"
    __table_args__ = (
        CheckConstraint(_CHECK_ROL, name="ck_sesion_usuario_rol"),
        Index("ix_sesion_usuario_actor", "actor_rol", "actor_id"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    sid_hash: Mapped[str] = mapped_column("sid_hash", String(64), nullable=False, unique=True)
    actor_rol: Mapped[str] = mapped_column("actor_rol", String(20), nullable=False)
    actor_id: Mapped[int] = mapped_column("actor_id", Integer, nullable=False)
    fecha_inicio: Mapped[datetime] = mapped_column("fecha_inicio", DateTime, nullable=False)
    fecha_expiracion: Mapped[datetime] = mapped_column("fecha_expiracion", DateTime, nullable=False)
    fecha_cierre: Mapped[datetime | None] = mapped_column("fecha_cierre", DateTime, nullable=True)
    motivo_cierre: Mapped[str | None] = mapped_column("motivo_cierre", String(20), nullable=True)

    def vigente(self, ahora: datetime) -> bool:
        return self.fecha_cierre is None and self.fecha_expiracion > ahora


class TokenRecuperacion(Base):
    """
    HU-28: enlace de recuperación de contraseña (un solo uso, vence en RECUPERACION_TTL_MIN).

    Igual que token_activacion (HU-27): el token va UNA vez por correo, en el fragmento de
    la URL, y en la BD solo queda su SHA-256. Pedir uno nuevo revoca los anteriores sin usar.
    """
    __tablename__ = "token_recuperacion"
    __table_args__ = (
        CheckConstraint(_CHECK_ROL, name="ck_token_recuperacion_rol"),
        Index("ix_token_recuperacion_actor", "actor_rol", "actor_id"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    actor_rol: Mapped[str] = mapped_column("actor_rol", String(20), nullable=False)
    actor_id: Mapped[int] = mapped_column("actor_id", Integer, nullable=False)
    token_hash: Mapped[str] = mapped_column("token_hash", String(64), nullable=False, unique=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_expiracion: Mapped[datetime] = mapped_column("fecha_expiracion", DateTime, nullable=False)
    fecha_uso: Mapped[datetime | None] = mapped_column("fecha_uso", DateTime, nullable=True)
    fecha_revocacion: Mapped[datetime | None] = mapped_column("fecha_revocacion", DateTime, nullable=True)

    def vigente(self, ahora: datetime) -> bool:
        return self.fecha_uso is None and self.fecha_revocacion is None and self.fecha_expiracion > ahora
