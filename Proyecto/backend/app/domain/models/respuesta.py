from datetime import date
from enum import Enum
from sqlalchemy import Integer, String, Text, Float, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class EstadoClasificacion(str, Enum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"

class FuenteClasificacion(str, Enum):
    USUARIO = "usuario"
    LLM = "llm"

class Respuesta(Base):
    __tablename__ = "respuestas"

    id: Mapped[int] = mapped_column("id_respuesta", Integer, primary_key=True)
    estado_clasificacion: Mapped[str | None] = mapped_column("estado_clasificacion", String(20), nullable=True)
    justificacion_usuario: Mapped[str | None] = mapped_column("justificacion_usuario", Text, nullable=True)
    matriz_controles_id_control: Mapped[int | None] = mapped_column(
        "Matriz_controles_id_control", Integer,
        ForeignKey("matriz_controles.id_control"), nullable=True
    )
    catalogo_brechas_id_brecha: Mapped[int | None] = mapped_column(
        "Catalogo_brechas_id_brecha", Integer, nullable=True
    )
    evaluacion_id: Mapped[int | None] = mapped_column(
        "Evaluacion_id", Integer,
        ForeignKey("evaluacion.id"), nullable=True
    )

    # --- Campos nuevos para clasificación automática ---
    estado_clasificacion_final: Mapped[str | None] = mapped_column(
        "estado_clasificacion_final", String(20), nullable=True
    )
    fuente_clasificacion: Mapped[str | None] = mapped_column(
        "fuente_clasificacion", String(10), nullable=True
    )
    confianza_clasificacion: Mapped[float | None] = mapped_column(
        "confianza_clasificacion", Float, nullable=True
    )
    fecha_validacion: Mapped[date | None] = mapped_column(
        "fecha_validacion", Date, nullable=True
    )

    evaluacion: Mapped["Evaluacion"] = relationship(back_populates="respuestas")
    evidencias: Mapped[list["Evidencia"]] = relationship(
        back_populates="respuesta",
        cascade="all, delete-orphan",
    )