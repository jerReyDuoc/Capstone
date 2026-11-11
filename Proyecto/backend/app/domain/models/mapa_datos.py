"""
HU-34 · Mapa de datos personales de la empresa cliente (base del RAT y del RoPA).

  mapa_datos           uno por empresa: la versión vigente del mapa (control de edición
                       concurrente), quién lo cambió por última vez y las sugerencias que la
                       empresa descartó.
  mapa_elemento        sistemas, bases de datos y terceros (criterio 1), con las categorías de
                       datos y de titulares del catálogo común (criterio 2). El RAT referenciará
                       estos elementos por su id.
  mapa_flujo           datos que viajan de un elemento a otro (entre sistemas, hacia terceros y
                       transferencias internacionales, que se calculan con el país de cada extremo).
  mapa_datos_version   criterio 5: una fila por cambio, con la instantánea COMPLETA del mapa, su
                       huella SHA-256 y las diferencias con la anterior. Es de solo inserción:
                       en PostgreSQL un trigger rechaza UPDATE y DELETE (como el audit_log).

Minimización (T-06): el mapa describe sistemas de la ORGANIZACIÓN. El responsable interno es un
cargo o un área; los textos libres se rechazan si traen correos, RUT o teléfonos
(app/domain/mapa_datos/modelo.py). Las categorías se guardan como listas de códigos del catálogo
(app/domain/catalogo_tratamiento.py), las mismas que usará el RAT.
"""
from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TIPOS_ELEMENTO = ("sistema", "base_datos", "tercero")
ORIGENES = ("manual", "plantilla", "evaluacion")
ACCIONES_VERSION = (
    "elemento_creado", "elemento_editado", "elemento_eliminado", "flujo_creado", "flujo_editado",
    "flujo_eliminado", "plantilla_aplicada", "sugerencia_aceptada", "revision_confirmada", "version_restaurada",
)


def _en(valores) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


class MapaDatos(Base):
    __tablename__ = "mapa_datos"
    __table_args__ = (
        UniqueConstraint("empresa_id", name="uq_mapa_datos_empresa"),
        CheckConstraint("version >= 0", name="ck_mapa_datos_version"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False)
    # Número de la última versión guardada (0 = aún sin cambios). Toda edición manda la que vio.
    version: Mapped[int] = mapped_column("version", Integer, nullable=False, default=0)
    plantilla_inicial: Mapped[str | None] = mapped_column("plantilla_inicial", String(30), nullable=True)
    sugerencias_descartadas: Mapped[list | None] = mapped_column("sugerencias_descartadas", JSON, nullable=True)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)


class MapaElemento(Base):
    __tablename__ = "mapa_elemento"
    __table_args__ = (
        CheckConstraint(f"tipo IN {_en(TIPOS_ELEMENTO)}", name="ck_mapa_elemento_tipo"),
        CheckConstraint(f"origen IN {_en(ORIGENES)}", name="ck_mapa_elemento_origen"),
        CheckConstraint("pais IS NULL OR length(pais) = 2", name="ck_mapa_elemento_pais"),
        CheckConstraint("tipo = 'tercero' OR (rol_tercero IS NULL AND contrato_firmado IS NULL)",
                        name="ck_mapa_elemento_rol_solo_tercero"),
        # Una plantilla o una sugerencia no agrega dos veces el mismo elemento
        UniqueConstraint("mapa_id", "clave", name="uq_mapa_elemento_clave"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    mapa_id: Mapped[int] = mapped_column(
        "mapa_id", Integer, ForeignKey("mapa_datos.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column("tipo", String(20), nullable=False)
    subtipo: Mapped[str | None] = mapped_column("subtipo", String(30), nullable=True)
    nombre: Mapped[str] = mapped_column("nombre", String(120), nullable=False)
    descripcion: Mapped[str | None] = mapped_column("descripcion", String(500), nullable=True)
    proveedor: Mapped[str | None] = mapped_column("proveedor", String(120), nullable=True)
    pais: Mapped[str | None] = mapped_column("pais", String(2), nullable=True)          # ISO 3166-1 alfa-2
    responsable: Mapped[str | None] = mapped_column("responsable", String(120), nullable=True)  # cargo o área
    categorias_datos: Mapped[list] = mapped_column("categorias_datos", JSON, nullable=False, default=list)
    categorias_titulares: Mapped[list] = mapped_column("categorias_titulares", JSON, nullable=False, default=list)
    nna_declarado: Mapped[bool] = mapped_column("nna_declarado", Boolean, nullable=False, default=False)
    rol_tercero: Mapped[str | None] = mapped_column("rol_tercero", String(20), nullable=True)
    contrato_firmado: Mapped[bool | None] = mapped_column("contrato_firmado", Boolean, nullable=True)
    origen: Mapped[str] = mapped_column("origen", String(15), nullable=False, default="manual")
    clave: Mapped[str | None] = mapped_column("clave", String(60), nullable=True)
    pendiente_revision: Mapped[bool] = mapped_column("pendiente_revision", Boolean, nullable=False, default=False)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)


class MapaFlujo(Base):
    __tablename__ = "mapa_flujo"
    __table_args__ = (
        CheckConstraint("origen_id <> destino_id", name="ck_mapa_flujo_extremos_distintos"),
        CheckConstraint(f"origen IN {_en(ORIGENES)}", name="ck_mapa_flujo_origen"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    mapa_id: Mapped[int] = mapped_column(
        "mapa_id", Integer, ForeignKey("mapa_datos.id", ondelete="CASCADE"), nullable=False, index=True)
    origen_id: Mapped[int] = mapped_column(
        "origen_id", Integer, ForeignKey("mapa_elemento.id", ondelete="CASCADE"), nullable=False, index=True)
    destino_id: Mapped[int] = mapped_column(
        "destino_id", Integer, ForeignKey("mapa_elemento.id", ondelete="CASCADE"), nullable=False, index=True)
    finalidad: Mapped[str | None] = mapped_column("finalidad", String(300), nullable=True)
    categorias_datos: Mapped[list] = mapped_column("categorias_datos", JSON, nullable=False, default=list)
    categorias_titulares: Mapped[list] = mapped_column("categorias_titulares", JSON, nullable=False, default=list)
    nna_declarado: Mapped[bool] = mapped_column("nna_declarado", Boolean, nullable=False, default=False)
    frecuencia: Mapped[str | None] = mapped_column("frecuencia", String(20), nullable=True)
    medio: Mapped[str | None] = mapped_column("medio", String(20), nullable=True)
    cifrado: Mapped[bool | None] = mapped_column("cifrado", Boolean, nullable=True)
    garantia: Mapped[str | None] = mapped_column("garantia", String(30), nullable=True)
    origen: Mapped[str] = mapped_column("origen", String(15), nullable=False, default="manual")
    clave: Mapped[str | None] = mapped_column("clave", String(60), nullable=True)
    pendiente_revision: Mapped[bool] = mapped_column("pendiente_revision", Boolean, nullable=False, default=False)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)


class MapaDatosVersion(Base):
    __tablename__ = "mapa_datos_version"
    __table_args__ = (
        UniqueConstraint("mapa_id", "numero", name="uq_mapa_datos_version_numero"),
        CheckConstraint(f"accion IN {_en(ACCIONES_VERSION)}", name="ck_mapa_datos_version_accion"),
        CheckConstraint("numero >= 1", name="ck_mapa_datos_version_numero"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    mapa_id: Mapped[int] = mapped_column("mapa_id", Integer, ForeignKey("mapa_datos.id"), nullable=False, index=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False)
    numero: Mapped[int] = mapped_column("numero", Integer, nullable=False)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    accion: Mapped[str] = mapped_column("accion", String(30), nullable=False)
    resumen: Mapped[str] = mapped_column("resumen", String(300), nullable=False)
    cambios: Mapped[list] = mapped_column("cambios", JSON, nullable=False, default=list)
    contenido: Mapped[dict] = mapped_column("contenido", JSON, nullable=False)
    huella: Mapped[str] = mapped_column("huella", String(64), nullable=False)
    elementos: Mapped[int] = mapped_column("elementos", Integer, nullable=False, default=0)
    flujos: Mapped[int] = mapped_column("flujos", Integer, nullable=False, default=0)
