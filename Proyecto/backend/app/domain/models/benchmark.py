from sqlalchemy import Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Benchmark(Base):
    """Estadísticas agregadas de puntajes por rubro y dominio."""
    __tablename__ = "benchmark"

    id_benchmark: Mapped[int] = mapped_column("id_benchmark", Integer, primary_key=True)
    promedio_puntaje: Mapped[float | None] = mapped_column("promedio_puntaje", Float, nullable=True)
    mediana_puntaje: Mapped[float | None] = mapped_column("mediana_puntaje", Float, nullable=True)
    puntaje_maximo: Mapped[float | None] = mapped_column("puntaje_maximo", Float, nullable=True)
    puntaje_minimo: Mapped[float | None] = mapped_column("puntaje_minimo", Float, nullable=True)
    total_evaluaciones: Mapped[int | None] = mapped_column(
        "total_evaluaciones", Integer, nullable=True
    )
    rubro_id: Mapped[int | None] = mapped_column(
        "Rubro_id",
        Integer,
        ForeignKey("rubro.id"),
        nullable=True,
    )
    dominio_id: Mapped[int | None] = mapped_column(
        "dominio_id",
        Integer,
        ForeignKey("dominio.id"),
        nullable=True,
    )