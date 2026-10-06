from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class RutaFormativa(Base):
    """Ruta de capacitación sugerida para cerrar una brecha detectada."""
    __tablename__ = "ruta_formativa"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    nombre: Mapped[str | None] = mapped_column(
        "nombre", String(100), nullable=True
    )