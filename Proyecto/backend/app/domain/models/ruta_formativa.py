from sqlalchemy import Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def _lineas(texto: str | None) -> tuple[str, ...]:
    return tuple(l.strip() for l in (texto or "").splitlines() if l.strip())


class RutaFormativa(Base):
    """
    Ruta de capacitación del catálogo formativo (HU-12).

    Una por dimensión normativa (dominio) y nivel (Inicial, Intermedio, Avanzado). Las
    brechas del catálogo apuntan a la ruta que las cierra (catalogo_brechas.ruta_formativa_id).
    objetivos_especificos y contenidos van uno por línea.
    """
    __tablename__ = "ruta_formativa"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    nombre: Mapped[str | None] = mapped_column(
        "nombre", String(100), nullable=True
    )
    # HU-12 (migración a9d3e5f7c1b2)
    dominio_id: Mapped[int | None] = mapped_column(
        "dominio_id", Integer, ForeignKey("dominio.id"), nullable=True
    )
    nivel: Mapped[str | None] = mapped_column("nivel", String(15), nullable=True)
    objetivo: Mapped[str | None] = mapped_column("objetivo", Text, nullable=True)
    objetivos_especificos: Mapped[str | None] = mapped_column("objetivos_especificos", Text, nullable=True)
    contenidos: Mapped[str | None] = mapped_column("contenidos", Text, nullable=True)
    horas: Mapped[int | None] = mapped_column("horas", Integer, nullable=True)
    modalidad: Mapped[str | None] = mapped_column("modalidad", String(50), nullable=True)
    publico_objetivo: Mapped[str | None] = mapped_column("publico_objetivo", String(150), nullable=True)

    @property
    def lista_objetivos(self) -> tuple[str, ...]:
        return _lineas(self.objetivos_especificos)

    @property
    def lista_contenidos(self) -> tuple[str, ...]:
        return _lineas(self.contenidos)
