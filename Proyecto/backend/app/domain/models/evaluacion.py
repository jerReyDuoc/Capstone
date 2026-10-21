from datetime import date
from sqlalchemy import Integer, Date, String, Boolean, ForeignKey, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


# Estados de `estado_progreso` en los que la evaluación ya no admite respuestas.
# "completada" es el estado que usa el benchmark (update_benchmark.py).
ESTADOS_CERRADOS = frozenset({"completada", "cerrada"})

# HU-19: de dónde viene la evaluación. Solo el backend la fija; el frontend nunca la envía.
ORIGEN_INVITACION = "invitacion"
ORIGEN_PUBLICA = "publica"
ORIGENES = frozenset({ORIGEN_INVITACION, ORIGEN_PUBLICA})


class Evaluacion(Base):
    __tablename__ = "evaluacion"

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    fecha_inicio: Mapped[date | None] = mapped_column("fecha_inicio", Date, nullable=True)
    estado_progreso: Mapped[str | None] = mapped_column("estado_progreso", String(20), nullable=True)
    usuario_temporal_id: Mapped[int | None] = mapped_column(
        "Usuario_temporal_id",
        Integer,
        ForeignKey("usuario_temporal.id"),
        nullable=True,
    )
    filtro_completado: Mapped[bool] = mapped_column(
        "filtro_completado", Boolean, default=False, nullable=False
    )
    fecha_filtro: Mapped[date | None] = mapped_column("fecha_filtro", Date, nullable=True)
    # Clave de acceso del encuestado anónimo (encuesta pública) para ejercer sus
    # derechos ARCOP. Solo se guarda el hash; NULL = sin acceso (o ya anonimizada).
    clave_acceso_hash: Mapped[str | None] = mapped_column("clave_acceso_hash", String(200), nullable=True)
    origen: Mapped[str] = mapped_column(
        "origen", String(20), nullable=False, default=ORIGEN_INVITACION, server_default=ORIGEN_INVITACION
    )
    # HU-19 criterio 4: las de prueba no entran al benchmark aunque estén completadas.
    # Solo la marca un admin (PATCH /api/evaluaciones/{id}/prueba).
    es_prueba: Mapped[bool] = mapped_column(
        "es_prueba", Boolean, nullable=False, default=False, server_default=sa_false()
    )

    respuestas: Mapped[list["Respuesta"]] = relationship(
        back_populates="evaluacion",
        cascade="all, delete-orphan",
    )

    @property
    def esta_cerrada(self) -> bool:
        return self.estado_progreso in ESTADOS_CERRADOS
