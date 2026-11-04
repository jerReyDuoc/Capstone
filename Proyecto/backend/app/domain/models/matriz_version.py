"""
HU-24 · Versiones de la matriz normativa y reglas de aplicabilidad.

matriz_version
  Cada versión guarda el contenido COMPLETO de la matriz (controles, brechas, rutas,
  preguntas de filtro y reglas) como JSON, con su huella SHA-256. Estados:

    borrador     la copia que el admin está editando (a lo más una). No la ve nadie más.
    publicada    la vigente (exactamente una). Las tablas matriz_controles, catalogo_brechas,
                 ruta_formativa, preguntas_filtro y regla_aplicabilidad la reflejan.
    reemplazada  una publicada anterior. Su contenido no cambia nunca: las evaluaciones
                 cerradas con ella la siguen usando (evaluacion.matriz_version_id).

  En PostgreSQL un trigger impide modificar el contenido de una versión que ya no es
  borrador y borrar versiones publicadas o reemplazadas (migración f8c2a6d4e1b7).

regla_aplicabilidad
  El árbol de la versión vigente, por id: (control, pregunta de filtro) = "el control se
  suma si responden SÍ a esa pregunta"; (control, NULL) = "aplica siempre" (pasada la
  compuerta). Se reescribe entera al publicar; la historia está en matriz_version.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ESTADO_BORRADOR = "borrador"
ESTADO_PUBLICADA = "publicada"
ESTADO_REEMPLAZADA = "reemplazada"
ESTADOS_VERSION = (ESTADO_BORRADOR, ESTADO_PUBLICADA, ESTADO_REEMPLAZADA)


class MatrizVersion(Base):
    __tablename__ = "matriz_version"
    __table_args__ = (
        # Exactamente una publicada y a lo más un borrador (también en la SQLite de las pruebas)
        Index("uq_matriz_version_una_publicada", "estado", unique=True,
              postgresql_where=text("estado = 'publicada'"), sqlite_where=text("estado = 'publicada'")),
        Index("uq_matriz_version_un_borrador", "estado", unique=True,
              postgresql_where=text("estado = 'borrador'"), sqlite_where=text("estado = 'borrador'")),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    # Etiqueta que elige el admin al publicar ("2026.2"). NULL mientras es borrador.
    etiqueta: Mapped[str | None] = mapped_column("etiqueta", String(30), nullable=True, unique=True)
    estado: Mapped[str] = mapped_column("estado", String(15), nullable=False, index=True)
    contenido: Mapped[dict] = mapped_column("contenido", JSON, nullable=False)
    # SHA-256 del contenido canónico (app/domain/matriz/contenido.py:huella). NULL en borrador.
    huella: Mapped[str | None] = mapped_column("huella", String(64), nullable=True)
    # Lo que queda en evaluacion.version_matriz y en el informe: "<etiqueta>+<8 hex>".
    version_texto: Mapped[str | None] = mapped_column("version_texto", String(40), nullable=True)
    nota_cambio: Mapped[str | None] = mapped_column("nota_cambio", String(1000), nullable=True)
    # Versión desde la que se creó el borrador (para detectar que otra se publicó entre medio)
    base_version_id: Mapped[int | None] = mapped_column(
        "base_version_id", Integer, ForeignKey("matriz_version.id"), nullable=True
    )
    # Control de edición concurrente del borrador: sube con cada cambio
    revision: Mapped[int] = mapped_column("revision", Integer, nullable=False, default=1, server_default="1")
    creado_por_admin_id: Mapped[int | None] = mapped_column(
        "creado_por_admin_id", Integer, ForeignKey("usuarios_admin.id_admin"), nullable=True
    )
    publicado_por_admin_id: Mapped[int | None] = mapped_column(
        "publicado_por_admin_id", Integer, ForeignKey("usuarios_admin.id_admin"), nullable=True
    )
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)
    fecha_publicacion: Mapped[datetime | None] = mapped_column("fecha_publicacion", DateTime, nullable=True)

    @property
    def es_borrador(self) -> bool:
        return self.estado == ESTADO_BORRADOR


class ReglaAplicabilidad(Base):
    __tablename__ = "regla_aplicabilidad"
    __table_args__ = (UniqueConstraint("control_id", "pregunta_filtro_id", name="uq_regla_aplicabilidad"),)

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    control_id: Mapped[int] = mapped_column(
        "control_id", Integer, ForeignKey("matriz_controles.id_control"), nullable=False, index=True
    )
    # NULL = el control aplica siempre (pasadas las compuertas)
    pregunta_filtro_id: Mapped[int | None] = mapped_column(
        "pregunta_filtro_id", Integer, ForeignKey("preguntas_filtro.id_pregunta"), nullable=True
    )
