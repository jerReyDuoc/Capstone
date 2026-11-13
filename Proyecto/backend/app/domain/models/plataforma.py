"""
HU-41 · Registro de tratamiento de la propia plataforma.

  plataforma_informe    una fila por emisión del RAT o del RoPA de ComplianceAI: código verificable, versión,
                        huella, si es oficial, cifras y los dos archivos (PDF y Excel) cifrados en STORAGE_DIR
                        con nombre UUID (no van a "Mis documentos": no son de una empresa cliente).
  plataforma_registro   fila única con los datos de contacto de Therion Labs y de su delegado de protección de
                        datos que pide el RoPA (mismo formato y validación que ropa_datos del cliente), cifrados en
                        reposo con la subclave "ropa" y nunca copiados a la bitácora.

  version   correlativo por tipo: sube cuando cambia la huella respecto de la emisión anterior de ese tipo.
  codigo    CIA-PLAT-REG-AAAA-NNNNNN-D o CIA-PLAT-ROPA-… (dígito verificador módulo 11 sobre el id).

En PostgreSQL un trigger impide cambiar o borrar una emisión una vez asignado su código.
"""
import json
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.cifrado_columnas import TextoCifradoRopa
from app.core.database import Base

TIPO_RAT = "rat"
TIPO_ROPA = "ropa"
TIPOS = (TIPO_RAT, TIPO_ROPA)
ID_REGISTRO = 1


class PlataformaInforme(Base):
    __tablename__ = "plataforma_informe"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_plataforma_informe_codigo"),
        CheckConstraint("tipo IN ('rat', 'ropa')", name="ck_plataforma_informe_tipo"),
        CheckConstraint("version >= 1", name="ck_plataforma_informe_version"),
        CheckConstraint("actividades >= 0", name="ck_plataforma_informe_actividades"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column("tipo", String(10), nullable=False, index=True)
    # NULL solo un instante: el código se calcula con el id recién asignado (misma transacción)
    codigo: Mapped[str | None] = mapped_column("codigo", String(40), nullable=True)
    version: Mapped[int] = mapped_column("version", Integer, nullable=False)
    huella: Mapped[str] = mapped_column("huella", String(64), nullable=False)
    oficial: Mapped[bool] = mapped_column("oficial", Boolean, nullable=False)
    motivos_borrador: Mapped[list] = mapped_column("motivos_borrador", JSON, nullable=False, default=list)
    actividades: Mapped[int] = mapped_column("actividades", Integer, nullable=False)
    # Cifras para listar y verificar sin regenerar (sin datos personales)
    resumen: Mapped[dict] = mapped_column("resumen", JSON, nullable=False, default=dict)
    aviso_version: Mapped[str] = mapped_column("aviso_version", String(40), nullable=False)
    archivo_pdf: Mapped[str] = mapped_column("archivo_pdf", String(500), nullable=False)
    archivo_xlsx: Mapped[str] = mapped_column("archivo_xlsx", String(500), nullable=False)
    hash_pdf: Mapped[str] = mapped_column("hash_pdf", String(64), nullable=False)
    hash_xlsx: Mapped[str] = mapped_column("hash_xlsx", String(64), nullable=False)
    nombre_pdf: Mapped[str] = mapped_column("nombre_pdf", String(120), nullable=False)
    nombre_xlsx: Mapped[str] = mapped_column("nombre_xlsx", String(120), nullable=False)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    emitido_por_admin_id: Mapped[int | None] = mapped_column(
        "emitido_por_admin_id", Integer, ForeignKey("usuarios_admin.id_admin"), nullable=True)


class PlataformaRegistro(Base):
    __tablename__ = "plataforma_registro"
    __table_args__ = (CheckConstraint("id = 1", name="ck_plataforma_registro_unica"),)

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    # JSON {direccion, correo, telefono, tiene_dpo, dpo_cargo, dpo_correo} (app/domain/ropa/datos.py), cifrado
    ropa_datos: Mapped[str] = mapped_column("ropa_datos", TextoCifradoRopa, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)
    actualizado_por_admin_id: Mapped[int | None] = mapped_column(
        "actualizado_por_admin_id", Integer, ForeignKey("usuarios_admin.id_admin"), nullable=True)

    def como_dict(self) -> dict:
        try:
            datos = json.loads(self.ropa_datos or "{}")
        except (TypeError, ValueError):       # ilegible (¿cambió la clave?): se vuelven a pedir
            datos = {}
        return datos if isinstance(datos, dict) else {}

    def guardar(self, datos: dict) -> None:
        self.ropa_datos = json.dumps(datos, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
