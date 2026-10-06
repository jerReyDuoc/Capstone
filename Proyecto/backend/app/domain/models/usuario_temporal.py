from datetime import date
from sqlalchemy import Integer, String, Date, ForeignKey
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