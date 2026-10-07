from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PreguntaFiltro(Base):
    """Las 7 preguntas de compuerta que determinan qué controles aplican."""
    __tablename__ = "preguntas_filtro"

    id_pregunta: Mapped[int] = mapped_column("id_pregunta", Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column("codigo", String(10), unique=True, nullable=False)
    orden: Mapped[int] = mapped_column("orden", Integer, nullable=False)
    pregunta: Mapped[str] = mapped_column("pregunta", String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column("descripcion", String(500), nullable=True)
    activa: Mapped[bool] = mapped_column("activa", Boolean, default=True, nullable=False)