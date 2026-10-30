from sqlalchemy import Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Benchmark(Base):
    """
    Estadísticas agregadas de puntajes por rubro y dominio.

    HU-10: una fila con dominio_id NULL guarda el puntaje GENERAL del rubro. Los valores de
    esta tabla son internos: hacia la API, la interfaz o el PDF solo salen a través de
    app/application/benchmark/k_anonimato.publicar(), que suprime las cohortes con menos de
    K_ANONIMATO_MINIMO empresas. puntaje_maximo y puntaje_minimo NUNCA se publican.
    """
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
    # HU-10: k = organizaciones distintas con puntaje (la base de la supresión) y la
    # distribución, que solo se publica con cohortes grandes (K_ANONIMATO_DISTRIBUCION).
    total_empresas: Mapped[int | None] = mapped_column("total_empresas", Integer, nullable=True)
    percentil_25: Mapped[float | None] = mapped_column("percentil_25", Float, nullable=True)
    percentil_75: Mapped[float | None] = mapped_column("percentil_75", Float, nullable=True)
