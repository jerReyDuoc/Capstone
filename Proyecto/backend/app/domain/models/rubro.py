from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class Rubro(Base):
    """Rubro o sector al que pertenece una organización evaluada."""
    __tablename__ = "rubro"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    nombre_rubro: Mapped[str | None] = mapped_column(
        "nombre_rubro", String(50), nullable=True
    )