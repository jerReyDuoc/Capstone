from datetime import date, datetime
from sqlalchemy import Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class UsuarioTemporal(Base):
    """Usuario invitado por link, sin registro completo. Expira en una fecha."""
    __tablename__ = "usuario_temporal"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    fecha_expiracion: Mapped[date | None] = mapped_column("fecha_expiracion", Date, nullable=True)
    email: Mapped[str | None] = mapped_column("email", String(100), nullable=True)
    validacion_invitacion: Mapped[str | None] = mapped_column(
        "validacion_invitacion", String(1), nullable=True
    )
    rubro_id: Mapped[int | None] = mapped_column(
        "Rubro_id",
        Integer,
        ForeignKey("rubro.id"),
        nullable=True,
    )
    # Se fija cuando se ejecuta una supresión ARCOP: el email y los textos del
    # usuario ya fueron borrados y no puede volver a obtener un token.
    fecha_anonimizacion: Mapped[datetime | None] = mapped_column(
        "fecha_anonimizacion", DateTime, nullable=True
    )
    # HU-04/HU-19: versión del aviso legal que aceptó y cuándo (UTC).
    aviso_legal_version: Mapped[str | None] = mapped_column("aviso_legal_version", String(20), nullable=True)
    fecha_aceptacion_aviso: Mapped[datetime | None] = mapped_column(
        "fecha_aceptacion_aviso", DateTime, nullable=True
    )
