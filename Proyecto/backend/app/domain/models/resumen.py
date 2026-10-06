from sqlalchemy import Integer, Float, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Resumen(Base):
    """Resumen agregado de resultados de una evaluación por dominio."""
    __tablename__ = "resumen"

    id_resumen: Mapped[int] = mapped_column("id_resumen", Integer, primary_key=True)
    puntaje_obtenido: Mapped[float | None] = mapped_column("puntaje_obtenido", Float, nullable=True)
    nivel_madurez: Mapped[str | None] = mapped_column("nivel_madurez", String(10), nullable=True)
    total_controles_evaluados: Mapped[int | None] = mapped_column(
        "total_controles_evaluados", Integer, nullable=True
    )
    evaluacion_id: Mapped[int | None] = mapped_column(
        "Evaluacion_id",
        Integer,
        ForeignKey("evaluacion.id"),
        nullable=True,
    )
    dominio_id: Mapped[int | None] = mapped_column(
        "dominio_id",
        Integer,
        ForeignKey("dominio.id"),
        nullable=True,
    )