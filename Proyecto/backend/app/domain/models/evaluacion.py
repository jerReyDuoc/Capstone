from datetime import date
from sqlalchemy import Integer, Date, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class Evaluacion(Base):
    __tablename__ = "evaluacion"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    fecha_inicio: Mapped[date | None] = mapped_column("fecha_inicio", Date, nullable=True)
    estado_progreso: Mapped[str | None] = mapped_column("estado_progreso", String(20), nullable=True)
    
    usuario_temporal_id: Mapped[int | None] = mapped_column(
        "Usuario_temporal_id",
        Integer,
        ForeignKey("usuario_temporal.id"),
        nullable=True,
    )

    respuestas: Mapped[list["Respuesta"]] = relationship(
        back_populates="evaluacion",
        cascade="all, delete-orphan",
    )