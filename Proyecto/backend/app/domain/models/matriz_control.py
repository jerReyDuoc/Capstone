from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class MatrizControl(Base):
    __tablename__ = "matriz_controles"

    id_control: Mapped[int] = mapped_column("id_control", Integer, primary_key=True)
    pregunta_evaluacion: Mapped[str | None] = mapped_column("pregunta_evaluacion", String(200), nullable=True)
    obligacion: Mapped[str | None] = mapped_column("obligacion", String(200), nullable=True)
    dominio_id: Mapped[int | None] = mapped_column("dominio_id", Integer, nullable=True)