from datetime import datetime
from enum import Enum
from sqlalchemy import Integer, String, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

# HU-27 (decisión del PO, 26-oct): un solo rol con acceso a todo el servicio pagado.
ROL_CLIENTE = "cliente"


class EstadoUsuarioDefinitivo(str, Enum):
    PENDIENTE_ACTIVACION = "pendiente_activacion"  # creado; aún no define su contraseña
    ACTIVO = "activo"                              # activó su cuenta con el enlace
    BLOQUEADO = "bloqueado"                        # lo deshabilitó un administrador

    @classmethod
    def valores(cls) -> list[str]:
        return [e.value for e in cls]


class UsuarioDefinitivo(Base):
    """
    HU-27: usuario definitivo de una empresa cliente (uno por empresa, rol `cliente`).

    Reemplaza al usuario temporal con el que la empresa hizo el autodiagnóstico. Sus
    datos de contacto (nombre, email) los ingresa el administrador y viven SOLO aquí:
    el email del usuario temporal y el contacto de la solicitud se borran al migrar.

    La contraseña la define el propio usuario con el enlace de activación de un solo
    uso (token_activacion); nunca se envía ni se guarda en claro: solo su hash PBKDF2.
    Mientras no la active, password_hash es NULL.
    """
    __tablename__ = "usuario_definitivo"
    __table_args__ = (
        CheckConstraint(f"rol = '{ROL_CLIENTE}'", name="ck_usuario_definitivo_rol"),
        CheckConstraint(
            "estado IN ('pendiente_activacion', 'activo', 'bloqueado')", name="ck_usuario_definitivo_estado"
        ),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(
        "empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, unique=True
    )
    nombre: Mapped[str] = mapped_column("nombre", String(120), nullable=False)
    # Siempre en minúsculas (se normaliza al crear); único en todo el sistema.
    email: Mapped[str] = mapped_column("email", String(100), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column("password_hash", String(200), nullable=True)
    rol: Mapped[str] = mapped_column("rol", String(20), nullable=False, default=ROL_CLIENTE,
                                     server_default=ROL_CLIENTE)
    estado: Mapped[str] = mapped_column(
        "estado", String(25), nullable=False,
        default=EstadoUsuarioDefinitivo.PENDIENTE_ACTIVACION.value,
        server_default=EstadoUsuarioDefinitivo.PENDIENTE_ACTIVACION.value,
    )
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_activacion: Mapped[datetime | None] = mapped_column("fecha_activacion", DateTime, nullable=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column("ultimo_acceso", DateTime, nullable=True)

    @property
    def activo(self) -> bool:
        return self.estado == EstadoUsuarioDefinitivo.ACTIVO.value and bool(self.password_hash)


class TokenActivacion(Base):
    """
    HU-27 criterio 3: enlace de activación de un solo uso y con vencimiento.

    El token (32 bytes aleatorios, base64url) se envía UNA vez por correo y en la BD solo
    queda su SHA-256: con un respaldo de la BD no se puede activar ninguna cuenta. Al
    usarlo se marca fecha_uso; generar uno nuevo revoca los anteriores sin usar.
    """
    __tablename__ = "token_activacion"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    usuario_definitivo_id: Mapped[int] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column("token_hash", String(64), nullable=False, unique=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_expiracion: Mapped[datetime] = mapped_column("fecha_expiracion", DateTime, nullable=False)
    fecha_uso: Mapped[datetime | None] = mapped_column("fecha_uso", DateTime, nullable=True)
    fecha_revocacion: Mapped[datetime | None] = mapped_column("fecha_revocacion", DateTime, nullable=True)
    creado_por_admin_id: Mapped[int | None] = mapped_column(
        "creado_por_admin_id", Integer, ForeignKey("usuarios_admin.id_admin"), nullable=True
    )

    def vigente(self, ahora: datetime) -> bool:
        return self.fecha_uso is None and self.fecha_revocacion is None and self.fecha_expiracion > ahora
