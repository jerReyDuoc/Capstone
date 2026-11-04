from sqlalchemy import Boolean, Integer, String, Text, ForeignKey, true as sa_true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.domain.models.ruta_formativa import RutaFormativa

class CatalogoBrechas(Base):
    __tablename__ = "catalogo_brechas"

    id_brecha: Mapped[int] = mapped_column("id_brecha", Integer, primary_key=True)
    codigo_brecha: Mapped[str | None] = mapped_column("codigo_brecha", String(20), nullable=True)
    categoria: Mapped[str | None] = mapped_column("categoria", String(50), nullable=True)
    comportamiento_detectado: Mapped[str | None] = mapped_column(
        "comportamiento_detectado", Text, nullable=True
    )
    criticidad: Mapped[str | None] = mapped_column("criticidad", String(10), nullable=True)
    accion_sistema: Mapped[str | None] = mapped_column("accion_sistema", String(100), nullable=True)
    ruta_formativa_id: Mapped[int | None] = mapped_column(
        "ruta_formativa_id", Integer, ForeignKey("ruta_formativa.id"), nullable=True
    )

    # HU-24: retirada en una versión de la matriz (no se borra: la usan evaluaciones anteriores)
    activo: Mapped[bool] = mapped_column(
        "activo", Boolean, nullable=False, default=True, server_default=sa_true()
    )

    ruta_formativa_rel: Mapped["RutaFormativa | None"] = relationship(
        "RutaFormativa",
        lazy="selectin",
    )

    @property
    def ruta_formativa(self) -> "RutaFormativa | None":
        """Alias que leen los schemas (BrechaResponse.ruta_formativa). Sin él la API
        devolvía siempre ruta_formativa = null y el panel no mostraba la ruta."""
        return self.ruta_formativa_rel
