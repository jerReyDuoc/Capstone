from sqlalchemy import Integer, String, Boolean, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PreguntaFiltro(Base):
    """
    Las preguntas del filtro inicial que determinan qué controles aplican.

    HU-24: `es_compuerta` marca las que, si se responden NO, dejan sin controles a la
    organización (F1 "¿usa IA?"). Las demás suman controles según regla_aplicabilidad.
    """
    __tablename__ = "preguntas_filtro"

    id_pregunta: Mapped[int] = mapped_column("id_pregunta", Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column("codigo", String(10), unique=True, nullable=False)
    orden: Mapped[int] = mapped_column("orden", Integer, nullable=False)
    pregunta: Mapped[str] = mapped_column("pregunta", String(500), nullable=False)
    descripcion: Mapped[str | None] = mapped_column("descripcion", String(500), nullable=True)
    activa: Mapped[bool] = mapped_column("activa", Boolean, default=True, nullable=False)
    es_compuerta: Mapped[bool] = mapped_column(
        "es_compuerta", Boolean, nullable=False, default=False, server_default=sa_false()
    )
