from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class UsuarioAdmin(Base):
    """
    Usuario administrador (rol admin_therion) con credenciales propias.
    Gestiona las solicitudes ARCOP. Se crea con:
        python -m app.core.crear_admin --email admin@ejemplo.cl
    La contraseña NUNCA se guarda en claro: solo su hash PBKDF2-SHA256.
    """
    __tablename__ = "usuarios_admin"

    id: Mapped[int] = mapped_column("id_admin", Integer, primary_key=True)
    email: Mapped[str] = mapped_column("email", String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column("password_hash", String(200), nullable=False)
    activo: Mapped[bool] = mapped_column("activo", Boolean, nullable=False, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    ultimo_acceso: Mapped[datetime | None] = mapped_column("ultimo_acceso", DateTime, nullable=True)
