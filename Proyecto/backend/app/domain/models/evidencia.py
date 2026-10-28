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

ORIGEN_CUESTIONARIO = "cuestionario"
ORIGEN_REMEDIACION = "remediacion"  # HU-17


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
    clasificacion_llm: Mapped[str | None] = mapped_column("clasificacion_llm", String(25), nullable=True)
    confianza: Mapped[float | None] = mapped_column("confianza", Float, nullable=True)
    justificacion_llm: Mapped[str | None] = mapped_column("justificacion_llm", Text, nullable=True)
    datos_extraidos: Mapped[dict | None] = mapped_column("datos_extraidos", JSON, nullable=True)
    errores_validacion: Mapped[list | None] = mapped_column("errores_validacion", JSON, nullable=True)
    fecha_subida: Mapped[date | None] = mapped_column("fecha_subida", Date, nullable=True)
    fecha_procesada: Mapped[date | None] = mapped_column("fecha_procesada", Date, nullable=True)

    # HU-17: de dónde viene la evidencia. "cuestionario" = durante el autodiagnóstico (HU-01/02);
    # "remediacion" = la empresa cliente la sube después, para re-evaluar un control con brecha.
    origen: Mapped[str] = mapped_column(
        "origen", String(15), nullable=False, default=ORIGEN_CUESTIONARIO, server_default=ORIGEN_CUESTIONARIO
    )
    # Solo remediación: el estado que la empresa dice haber alcanzado, su justificación
    # (anonimizada, HU-06), el estado vigente antes de procesar y el que quedó después.
    estado_declarado: Mapped[str | None] = mapped_column("estado_declarado", String(25), nullable=True)
    justificacion_remediacion: Mapped[str | None] = mapped_column("justificacion_remediacion", Text, nullable=True)
    estado_previo: Mapped[str | None] = mapped_column("estado_previo", String(25), nullable=True)
    estado_resultante: Mapped[str | None] = mapped_column("estado_resultante", String(25), nullable=True)
    # HU-17 C2: términos del control encontrados en el texto (verificación local, sin LLM)
    terminos_control: Mapped[dict | None] = mapped_column("terminos_control", JSON, nullable=True)

    @property
    def es_remediacion(self) -> bool:
        return self.origen == ORIGEN_REMEDIACION

    respuesta_id: Mapped[int] = mapped_column(
        "Respuestas_id_respuesta", Integer,
        ForeignKey("respuestas.id_respuesta"), nullable=False
    )
    respuesta: Mapped["Respuesta"] = relationship(back_populates="evidencias")