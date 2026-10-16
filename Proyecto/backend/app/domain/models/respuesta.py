from datetime import date
from enum import Enum
from sqlalchemy import Integer, String, Text, Float, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

class EstadoClasificacion(str, Enum):
    CUMPLIDO = "cumplido"
    PARCIALMENTE_CUMPLIDO = "parcialmente_cumplido"
    NO_CUMPLIDO = "no_cumplido"
    NO_APLICA = "no_aplica"
    # HU-02 (decisión del PO, 16-oct): el usuario PUEDE declararla cuando no sabe
    # cómo clasificar el control; adjunta evidencia y el LLM decide si es cumplido,
    # parcialmente cumplido o no cumplido. Mientras no se resuelva puntúa 0.
    # El backend también la asigna cuando la capa de seguridad bloquea una evidencia.
    REQUIERE_REVISION = "requiere_revision"

    @classmethod
    def requiere_evidencia(cls, valor: str) -> bool:
        """Estados que admiten (y esperan) evidencia para que el LLM la valide."""
        return valor in (
            cls.CUMPLIDO.value,
            cls.PARCIALMENTE_CUMPLIDO.value,
            cls.REQUIERE_REVISION.value,
        )

    @classmethod
    def requiere_justificacion(cls, valor: str) -> bool:
        """HU-02 C2: la justificación es obligatoria (con largo mínimo) en estos estados."""
        return valor in (cls.PARCIALMENTE_CUMPLIDO.value, cls.REQUIERE_REVISION.value)

    @classmethod
    def declarables(cls) -> list[str]:
        """Los 5 estados de la matriz que el usuario puede elegir al responder (HU-02)."""
        return [
            cls.CUMPLIDO.value,
            cls.PARCIALMENTE_CUMPLIDO.value,
            cls.NO_CUMPLIDO.value,
            cls.NO_APLICA.value,
            cls.REQUIERE_REVISION.value,
        ]

    @classmethod
    def resolutivos(cls) -> list[str]:
        """Estados con los que la revisión humana puede CERRAR un control: todos
        menos 'requiere_revision' (revisar es justamente resolverlo)."""
        return [v for v in cls.declarables() if v != cls.REQUIERE_REVISION.value]

class FuenteClasificacion(str, Enum):
    USUARIO = "usuario"
    LLM = "llm"
    SEGURIDAD = "seguridad"  # decisión tomada por la capa anti prompt-injection
    REVISION = "revision"    # decisión del Oficial de Cumplimiento (revisión humana)

class Respuesta(Base):
    __tablename__ = "respuestas"
    # HU-01: una sola respuesta por control en cada evaluación. Responder de nuevo
    # un control ACTUALIZA la fila existente (POST /api/respuestas es un upsert).
    # El índice único también acelera las consultas por evaluación (progreso).
    __table_args__ = (
        UniqueConstraint(
            "Evaluacion_id", "Matriz_controles_id_control",
            name="uq_respuesta_evaluacion_control",
        ),
    )

    id: Mapped[int] = mapped_column("id_respuesta", Integer, primary_key=True)
    estado_clasificacion: Mapped[str | None] = mapped_column(
        "estado_clasificacion", String(25), nullable=True
    )
    justificacion_usuario: Mapped[str | None] = mapped_column(
        "justificacion_usuario", Text, nullable=True
    )
    matriz_controles_id_control: Mapped[int | None] = mapped_column(
        "Matriz_controles_id_control",
        Integer,
        ForeignKey("matriz_controles.id_control"),
        nullable=True,
    )
    catalogo_brechas_id_brecha: Mapped[int | None] = mapped_column(
        "Catalogo_brechas_id_brecha",
        Integer,
        ForeignKey("catalogo_brechas.id_brecha"),
        nullable=True,
    )
    evaluacion_id: Mapped[int | None] = mapped_column(
        "Evaluacion_id",
        Integer,
        ForeignKey("evaluacion.id"),
        nullable=True,
    )

    estado_clasificacion_final: Mapped[str | None] = mapped_column(
        "estado_clasificacion_final", String(25), nullable=True
    )
    fuente_clasificacion: Mapped[str | None] = mapped_column(
        "fuente_clasificacion", String(10), nullable=True
    )
    confianza_clasificacion: Mapped[float | None] = mapped_column(
        "confianza_clasificacion", Float, nullable=True
    )
    fecha_validacion: Mapped[date | None] = mapped_column(
        "fecha_validacion", Date, nullable=True
    )

    # Revisión humana (Oficial de Cumplimiento). Es la "verdad de referencia" con la
    # que se mide la precisión del LLM en /api/ia/metricas.
    clasificacion_revisada: Mapped[str | None] = mapped_column(
        "clasificacion_revisada", String(25), nullable=True
    )
    fecha_revision: Mapped[date | None] = mapped_column(
        "fecha_revision", Date, nullable=True
    )

    def sincronizar_brecha(self, control) -> None:
        """
        Regla de negocio única para la brecha (HU-02): una respuesta tiene la brecha
        de su control si y solo si su estado VIGENTE (estado_clasificacion_final) es
        'no_cumplido'. Se llama cada vez que cambia ese estado: declaración del
        usuario, decisión del LLM, bloqueo de seguridad o revisión humana.
        """
        if self.estado_clasificacion_final != EstadoClasificacion.NO_CUMPLIDO.value:
            self.catalogo_brechas_id_brecha = None
        elif control is not None and control.catalogo_brechas_id_brecha:
            self.catalogo_brechas_id_brecha = control.catalogo_brechas_id_brecha

    evaluacion: Mapped["Evaluacion"] = relationship(back_populates="respuestas")
    evidencias: Mapped[list["Evidencia"]] = relationship(
        back_populates="respuesta",
        cascade="all, delete-orphan",
    )