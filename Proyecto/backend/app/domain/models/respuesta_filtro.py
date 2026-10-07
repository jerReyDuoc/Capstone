from datetime import date
from sqlalchemy import Integer, Boolean, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.domain.models.pregunta_filtro import PreguntaFiltro

class RespuestaFiltro(Base):
    """Respuesta SI/NO de un usuario a una de las 7 preguntas de compuerta."""
    __tablename__ = "respuestas_filtro"
    __table_args__ = (
        UniqueConstraint("Evaluacion_id", "pregunta_id", name="uq_respuesta_filtro_eval_pregunta"),
    )

    id_respuesta_filtro: Mapped[int] = mapped_column(
        "id_respuesta_filtro", Integer, primary_key=True
    )
    evaluacion_id: Mapped[int] = mapped_column(
        "Evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=False
    )
    pregunta_id: Mapped[int] = mapped_column(
        "pregunta_id", Integer, ForeignKey("preguntas_filtro.id_pregunta"), nullable=False
    )
    respuesta: Mapped[bool] = mapped_column("respuesta", Boolean, nullable=False)
    fecha_respuesta: Mapped[date] = mapped_column("fecha_respuesta", Date, nullable=False)

    pregunta: Mapped["PreguntaFiltro"] = relationship("PreguntaFiltro", lazy="selectin")