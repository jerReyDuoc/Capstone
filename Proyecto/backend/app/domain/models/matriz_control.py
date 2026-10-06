from sqlalchemy import Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class MatrizControl(Base):
    __tablename__ = "matriz_controles"

    id_control: Mapped[int] = mapped_column("id_control", Integer, primary_key=True)
    codigo_control: Mapped[str | None] = mapped_column("codigo_control", String(20), nullable=True)
    framework_fuente: Mapped[str | None] = mapped_column("framework_fuente", String(50), nullable=True)
    articulo_referencia: Mapped[str | None] = mapped_column("articulo_referencia", String(100), nullable=True)
    tipo_fuente: Mapped[str | None] = mapped_column("tipo_fuente", String(50), nullable=True)
    obligacion: Mapped[str | None] = mapped_column("obligacion", String(200), nullable=True)
    pregunta_evaluacion: Mapped[str | None] = mapped_column("pregunta_evaluacion", String(500), nullable=True)
    aplicabilidad: Mapped[str | None] = mapped_column("aplicabilidad", String(100), nullable=True)
    evidencia_esperada: Mapped[str | None] = mapped_column("evidencia_esperada", Text, nullable=True)
    criticidad: Mapped[str | None] = mapped_column("criticidad", String(10), nullable=True)
    recomendacion: Mapped[str | None] = mapped_column("recomendacion", Text, nullable=True)
    test_asociado: Mapped[str | None] = mapped_column("test_asociado", String(100), nullable=True)
    dominio_id: Mapped[int | None] = mapped_column(
        "dominio_id", Integer, ForeignKey("dominio.id"), nullable=True
    )
    catalogo_brechas_id_brecha: Mapped[int | None] = mapped_column(
        "catalogo_brechas_id_brecha", Integer,
        ForeignKey("catalogo_brechas.id_brecha"), nullable=True
    )