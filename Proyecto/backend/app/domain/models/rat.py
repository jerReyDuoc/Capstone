"""
HU-35 · Registro de Actividades de Tratamiento (RAT) de la empresa cliente.

  rat_actividad          la ficha de trabajo de cada actividad: estado (borrador | en_revision |
                         vigente | archivada), contenido (JSON, ver app/domain/rat/modelo.py) con los
                         ids de los elementos y flujos ELEGIDOS DEL MAPA (HU-34), el número de la
                         versión vigente y los motivos de revisión cuando el mapa la afecta.
  rat_actividad_version  una fila por cada vez que la actividad queda vigente, con la instantánea
                         COMPLETA y su huella SHA-256. Es inmutable: en PostgreSQL un trigger rechaza
                         UPDATE y DELETE (como la matriz versionada de HU-24).

En PostgreSQL otro trigger impide cambiar el contenido de una actividad mientras está vigente: para
editarla se abre una nueva versión (vuelve a borrador) y la vigente anterior sigue valiendo.

La versión vigente se guarda por su NÚMERO (no con una llave foránea) para no crear un ciclo entre
las dos tablas.
"""
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ESTADOS_RAT = ("borrador", "en_revision", "vigente", "archivada")


def _en(valores) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


class RatActividad(Base):
    __tablename__ = "rat_actividad"
    __table_args__ = (
        CheckConstraint(f"estado IN {_en(ESTADOS_RAT)}", name="ck_rat_actividad_estado"),
        CheckConstraint(f"estado_previo IS NULL OR estado_previo IN {_en(ESTADOS_RAT)}",
                        name="ck_rat_actividad_estado_previo"),
        CheckConstraint("revision >= 1", name="ck_rat_actividad_revision"),
        CheckConstraint("completitud BETWEEN 0 AND 100", name="ck_rat_actividad_completitud"),
        # Una vigente siempre tiene su versión guardada
        CheckConstraint("estado <> 'vigente' OR version_vigente IS NOT NULL", name="ck_rat_actividad_vigente"),
        CheckConstraint("origen IN ('manual', 'ia')", name="ck_rat_actividad_origen"),  # HU-39
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column("nombre", String(150), nullable=False)
    estado: Mapped[str] = mapped_column("estado", String(15), nullable=False, default="borrador")
    # Estado antes de archivarla (para reactivarla)
    estado_previo: Mapped[str | None] = mapped_column("estado_previo", String(15), nullable=True)
    contenido: Mapped[dict] = mapped_column("contenido", JSON, nullable=False)
    # Control de edición concurrente: sube con cada cambio (toda edición manda la que vio)
    revision: Mapped[int] = mapped_column("revision", Integer, nullable=False, default=1)
    # Porcentaje de completitud la última vez que se guardó (para listar y filtrar sin recalcular)
    completitud: Mapped[int] = mapped_column("completitud", Integer, nullable=False, default=0)
    # Número de la última versión que quedó vigente (NULL si nunca lo estuvo)
    version_vigente: Mapped[int | None] = mapped_column("version_vigente", Integer, nullable=True)
    # Por qué está en revisión: [{fecha, texto, version_mapa}] (cambios del mapa que la afectan)
    motivos_revision: Mapped[list] = mapped_column("motivos_revision", JSON, nullable=False, default=list)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    # HU-39: "manual" o "ia" (propuesta del asistente aceptada por el usuario) y qué propuesta la creó
    origen: Mapped[str] = mapped_column("origen", String(10), nullable=False, default="manual")
    propuesta_ia_id: Mapped[int | None] = mapped_column(
        "propuesta_ia_id", Integer, ForeignKey("asistente_propuesta.id", ondelete="SET NULL"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)
    fecha_vigencia: Mapped[datetime | None] = mapped_column("fecha_vigencia", DateTime, nullable=True)
    fecha_archivo: Mapped[datetime | None] = mapped_column("fecha_archivo", DateTime, nullable=True)


class RatActividadVersion(Base):
    __tablename__ = "rat_actividad_version"
    __table_args__ = (
        UniqueConstraint("actividad_id", "numero", name="uq_rat_actividad_version_numero"),
        CheckConstraint("numero >= 1", name="ck_rat_actividad_version_numero"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    actividad_id: Mapped[int] = mapped_column(
        "actividad_id", Integer, ForeignKey("rat_actividad.id"), nullable=False, index=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False)
    numero: Mapped[int] = mapped_column("numero", Integer, nullable=False)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    contenido: Mapped[dict] = mapped_column("contenido", JSON, nullable=False)
    huella: Mapped[str] = mapped_column("huella", String(64), nullable=False)
    # Versión del mapa de datos con que se calculó lo que la actividad toma del mapa
    version_mapa: Mapped[int] = mapped_column("version_mapa", Integer, nullable=False, default=0)
    # Qué cambió respecto de la versión vigente anterior (texto para el historial)
    resumen: Mapped[str] = mapped_column("resumen", String(300), nullable=False)
    cambios: Mapped[list] = mapped_column("cambios", JSON, nullable=False, default=list)
