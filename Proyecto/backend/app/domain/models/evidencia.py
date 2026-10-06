from datetime import date
from enum import Enum
from sqlalchemy import Integer, String, Text, Float, Date, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class EstadoValidacion(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    VALIDATED = "validated"
    REJECTED = "rejected"
    ERROR = "error"

class Evidencia(Base):
    __tablename__ = "evidencias"

    id_evidencia: Mapped[int] = mapped_column("id_evidencia", Integer, primary_key=True)
    nombre_archivo: Mapped[str] = mapped_column("nombre_archivo", String(255))
    storage_path: Mapped[str] = mapped_column("storage_path", String(512))
    mime_type: Mapped[str] = mapped_column("mime_type", String(100))
    hash_archivo: Mapped[str] = mapped_column("hash_archivo", String(64), index=True)
    estado_validacion: Mapped[str] = mapped_column(
        "estado_validacion", String(20), default=EstadoValidacion.PENDING.value
    )
    clasificacion_llm: Mapped[str | None] = mapped_column("clasificacion_llm", String(20), nullable=True)
    confianza: Mapped[float | None] = mapped_column("confianza", Float, nullable=True)
    justificacion_llm: Mapped[str | None] = mapped_column("justificacion_llm", Text, nullable=True)
    datos_extraidos: Mapped[dict | None] = mapped_column("datos_extraidos", JSON, nullable=True)
    errores_validacion: Mapped[list | None] = mapped_column("errores_validacion", JSON, nullable=True)
    fecha_subida: Mapped[date | None] = mapped_column("fecha_subida", Date, nullable=True)
    fecha_procesada: Mapped[date | None] = mapped_column("fecha_procesada", Date, nullable=True)

    respuesta_id: Mapped[int] = mapped_column(
        "Respuestas_id_respuesta", Integer,
        ForeignKey("respuestas.id_respuesta"), nullable=False
    )
    respuesta: Mapped["Respuesta"] = relationship(back_populates="evidencias")