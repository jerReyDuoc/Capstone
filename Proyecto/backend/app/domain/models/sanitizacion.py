from datetime import datetime
from sqlalchemy import Integer, String, Text, Boolean, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Sanitizacion(Base):
    """
    Mapa de entidades anonimizadas de un texto (auditoría Ley 21.719).
    NUNCA se envía al proveedor LLM.

    - `entidades`: metadatos en claro sin PII -> [{tipo, inicio, fin, fuente, huella}]
      (`huella` = HMAC del valor: permite buscar coincidencias sin descifrar).
    - `mapa_cifrado`: token Fernet con [{tipo, inicio, fin, valor}] (valores originales).
      HU-06 (decisión del PO): queda en NULL salvo GUARDAR_MAPA_ENTIDADES_CIFRADO=true,
      para que la anonimización sea irreversible.
    """
    __tablename__ = "sanitizaciones"

    id_sanitizacion: Mapped[int] = mapped_column("id_sanitizacion", Integer, primary_key=True)
    traza_id: Mapped[str] = mapped_column("traza_id", String(32), nullable=False, index=True)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    campo: Mapped[str] = mapped_column("campo", String(30), nullable=False)

    motor: Mapped[str] = mapped_column("motor", String(120), nullable=False)
    duracion_ms: Mapped[float] = mapped_column("duracion_ms", Float, nullable=False)
    truncado: Mapped[bool] = mapped_column("truncado", Boolean, nullable=False, default=False)

    total_entidades: Mapped[int] = mapped_column("total_entidades", Integer, nullable=False, default=0)
    conteo_por_tipo: Mapped[dict | None] = mapped_column("conteo_por_tipo", JSON, nullable=True)
    entidades: Mapped[list | None] = mapped_column("entidades", JSON, nullable=True)
    mapa_cifrado: Mapped[str | None] = mapped_column("mapa_cifrado", Text, nullable=True)

    evaluacion_id: Mapped[int | None] = mapped_column(
        "Evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=True
    )
    respuesta_id: Mapped[int | None] = mapped_column(
        "Respuestas_id_respuesta", Integer, ForeignKey("respuestas.id_respuesta"), nullable=True
    )
    evidencia_id: Mapped[int | None] = mapped_column(
        "Evidencias_id_evidencia", Integer, ForeignKey("evidencias.id_evidencia"), nullable=True, index=True
    )
