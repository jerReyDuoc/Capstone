"""
HU-09 · Modelos del Auditor Externo y de la verificación por lote del audit_log.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ALGORITMO_LOTE = "sha256-v1"


class AuditLogSello(Base):
    """
    Sello de un lote CONSECUTIVO de filas de audit_log (criterio 3: integridad por hash en lote).

      hash_lote = SHA-256( "\\n".join( SHA-256("<id>|" + canónico(fila)) ) )   en orden de id
      sello     = SHA-256( canónico(lote, desde_id, hasta_id, cantidad, hash_lote, fecha, sello_anterior) )
      firma     = HMAC-SHA256(clave de la bitácora, sello)

    `hash_lote` y `sello` son SHA-256 sin clave: el Auditor Externo los recalcula con el
    archivo exportado y el script que va dentro (sin pedirnos nada). Si se borra, agrega,
    altera o reordena una fila del lote, su hash_lote cambia; si se altera un sello, se rompe
    la cadena de sellos. `firma` (con clave) prueba ante nosotros que el sello lo emitió el
    sistema y no alguien con acceso directo a la BD.

    Igual que audit_log: solo inserción (permisos + triggers en PostgreSQL).
    """
    __tablename__ = "audit_log_sello"
    __table_args__ = (
        UniqueConstraint("desde_id", name="uq_audit_log_sello_desde"),
        UniqueConstraint("hasta_id", name="uq_audit_log_sello_hasta"),
    )

    # Número de lote (1, 2, 3...): lo asigna el sellado (es parte del sello), no una secuencia
    id: Mapped[int] = mapped_column("id", Integer, primary_key=True, autoincrement=False)
    desde_id: Mapped[int] = mapped_column("desde_id", Integer, nullable=False)
    hasta_id: Mapped[int] = mapped_column("hasta_id", Integer, nullable=False)
    cantidad: Mapped[int] = mapped_column("cantidad", Integer, nullable=False)
    hash_lote: Mapped[str] = mapped_column("hash_lote", String(64), nullable=False)
    sello_anterior: Mapped[str] = mapped_column("sello_anterior", String(64), nullable=False)
    sello: Mapped[str] = mapped_column("sello", String(64), nullable=False, unique=True)
    firma: Mapped[str] = mapped_column("firma", String(64), nullable=False)
    algoritmo: Mapped[str] = mapped_column("algoritmo", String(20), nullable=False, default=ALGORITMO_LOTE)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)


class UsuarioAuditor(Base):
    """
    Cuenta del Auditor Externo (rol `auditor_externo`): SOLO LECTURA del audit_log.

    Puede consultar, verificar y exportar el log; no ve ni cambia nada más del sistema.
    La cuenta vence (`fecha_expiracion`, máx. AUDITOR_VIGENCIA_MAX_DIAS): la auditoría es una
    actividad acotada. La crea un admin (POST /api/admin/auditores o
    `python -m app.core.crear_auditor`) y cada acceso del auditor queda en el propio log.
    `organizacion` es la firma auditora (no un dato personal); no se guarda su nombre.
    """
    __tablename__ = "usuario_auditor"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    email: Mapped[str] = mapped_column("email", String(100), nullable=False, unique=True)
    organizacion: Mapped[str] = mapped_column("organizacion", String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column("password_hash", String(200), nullable=False)
    activo: Mapped[bool] = mapped_column("activo", Boolean, nullable=False, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_expiracion: Mapped[datetime] = mapped_column("fecha_expiracion", DateTime, nullable=False)
    creado_por_admin_id: Mapped[int | None] = mapped_column(
        "creado_por_admin_id", Integer, ForeignKey("usuarios_admin.id_admin"), nullable=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column("ultimo_acceso", DateTime, nullable=True)

    def vigente(self, ahora: datetime) -> bool:
        return bool(self.activo and self.fecha_expiracion and self.fecha_expiracion > ahora)
