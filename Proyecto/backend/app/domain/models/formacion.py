"""
HU-26: recorrido de los módulos formativos y avance de la empresa cliente.

Un "módulo" del plan formativo (HU-12) es una ruta del catálogo (ruta_formativa). Para
recorrerlo en la plataforma, cada ruta tiene:

  - leccion_formativa       sus lecciones en orden (contenido y material de apoyo; por ahora
                            placeholders, decisión del PO del 26-oct: "cursos con placeholders").
  - pregunta_verificacion   la actividad de verificación del final (selección única). La
                            respuesta correcta NUNCA sale por la API: corrige el servidor.

El avance es de la EMPRESA (un usuario por empresa, HU-27): una fila por empresa y módulo
en avance_formativo, con lo iniciado, lo completado, la fecha y el código de la constancia.
Completar un módulo NO cambia el puntaje de madurez: eso solo pasa con evidencia nueva
(HU-17, app/application/use_cases/remediacion.py).
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EstadoAvance(str, Enum):
    EN_CURSO = "en_curso"        # vio al menos una lección
    COMPLETADO = "completado"    # aprobó la actividad de verificación

    @classmethod
    def valores(cls) -> list[str]:
        return [e.value for e in cls]


# Estado que se muestra cuando la empresa aún no abre el módulo (no hay fila).
NO_INICIADO = "no_iniciado"


class LeccionFormativa(Base):
    """Lección de un módulo. `material_apoyo` es una lista de {tipo, titulo, descripcion}."""
    __tablename__ = "leccion_formativa"
    __table_args__ = (UniqueConstraint("ruta_formativa_id", "orden", name="uq_leccion_ruta_orden"),)

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    ruta_formativa_id: Mapped[int] = mapped_column(
        "ruta_formativa_id", Integer, ForeignKey("ruta_formativa.id"), nullable=False, index=True
    )
    orden: Mapped[int] = mapped_column("orden", Integer, nullable=False)
    titulo: Mapped[str] = mapped_column("titulo", String(200), nullable=False)
    resumen: Mapped[str | None] = mapped_column("resumen", Text, nullable=True)
    # Cuerpo de la lección, un párrafo por línea (placeholder hasta que Therion Labs cargue el real)
    contenido: Mapped[str | None] = mapped_column("contenido", Text, nullable=True)
    material_apoyo: Mapped[list | None] = mapped_column("material_apoyo", JSON, nullable=True)
    duracion_min: Mapped[int | None] = mapped_column("duracion_min", Integer, nullable=True)


class PreguntaVerificacion(Base):
    """Pregunta de selección única de la actividad final. `opciones` es una lista de textos."""
    __tablename__ = "pregunta_verificacion"
    __table_args__ = (UniqueConstraint("ruta_formativa_id", "orden", name="uq_pregunta_ruta_orden"),)

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    ruta_formativa_id: Mapped[int] = mapped_column(
        "ruta_formativa_id", Integer, ForeignKey("ruta_formativa.id"), nullable=False, index=True
    )
    orden: Mapped[int] = mapped_column("orden", Integer, nullable=False)
    enunciado: Mapped[str] = mapped_column("enunciado", Text, nullable=False)
    opciones: Mapped[list] = mapped_column("opciones", JSON, nullable=False)
    # Índice (desde 0) de la opción correcta. Solo lo lee el servidor al corregir.
    correcta: Mapped[int] = mapped_column("correcta", Integer, nullable=False)
    explicacion: Mapped[str | None] = mapped_column("explicacion", Text, nullable=True)


class AvanceFormativo(Base):
    """
    Avance de la empresa en un módulo. Lo crea la primera lección vista; aprobar la
    actividad de verificación lo deja en `completado` con su fecha y código de constancia.
    """
    __tablename__ = "avance_formativo"
    __table_args__ = (
        UniqueConstraint("empresa_id", "ruta_formativa_id", name="uq_avance_empresa_ruta"),
        CheckConstraint("estado IN ('en_curso', 'completado')", name="ck_avance_formativo_estado"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    ruta_formativa_id: Mapped[int] = mapped_column(
        "ruta_formativa_id", Integer, ForeignKey("ruta_formativa.id"), nullable=False
    )
    # Evaluación cuyo plan llevó a abrir el módulo (informativo: el avance vale para la empresa)
    evaluacion_id: Mapped[int | None] = mapped_column(
        "evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=True
    )
    # Quién lo registró (el único usuario definitivo de la empresa)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True
    )
    estado: Mapped[str] = mapped_column("estado", String(15), nullable=False, default=EstadoAvance.EN_CURSO.value)
    lecciones_vistas: Mapped[list | None] = mapped_column("lecciones_vistas", JSON, nullable=True)
    intentos: Mapped[int] = mapped_column("intentos", Integer, nullable=False, default=0)
    ultimo_puntaje: Mapped[float | None] = mapped_column("ultimo_puntaje", Float, nullable=True)
    mejor_puntaje: Mapped[float | None] = mapped_column("mejor_puntaje", Float, nullable=True)
    fecha_inicio: Mapped[datetime] = mapped_column("fecha_inicio", DateTime, nullable=False)
    fecha_ultima_actividad: Mapped[datetime] = mapped_column("fecha_ultima_actividad", DateTime, nullable=False)
    fecha_completado: Mapped[datetime | None] = mapped_column("fecha_completado", DateTime, nullable=True)
    # Código aleatorio impreso en la constancia (CF-XXXX-XXXX); único.
    codigo_constancia: Mapped[str | None] = mapped_column("codigo_constancia", String(20), nullable=True, unique=True)

    @property
    def completado(self) -> bool:
        return self.estado == EstadoAvance.COMPLETADO.value

    @property
    def ids_vistas(self) -> set[int]:
        return {int(i) for i in (self.lecciones_vistas or [])}
