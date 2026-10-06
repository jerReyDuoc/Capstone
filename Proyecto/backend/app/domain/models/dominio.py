from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Dominio(Base):
    """Dominio o categoría temática a la que pertenece un control."""
    __tablename__ = "dominio"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    nombre_dominio: Mapped[str | None] = mapped_column(
        "nombre_dominio", String(50), nullable=True
    )