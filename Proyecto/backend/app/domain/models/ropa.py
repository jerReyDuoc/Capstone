"""
HU-37 · Informe RoPA del registro de actividades de tratamiento.

  ropa_datos     una fila por empresa: los datos que el RoPA pide y el registro no tiene (contacto de la
                 empresa, delegado de protección de datos y el contacto de cada organización por cuenta de la
                 cual la empresa actúa como encargada). Se piden una vez y se reutilizan. Son datos de
                 contacto: van cifrados en reposo (TextoCifradoRopa) y nunca se copian a la bitácora.
  ropa_informe   una fila por emisión del informe RoPA: código verificable, versión, huella, partes
                 incluidas (responsable, encargado), conteos y los documentos que quedaron en
                 "Mis documentos" (PDF y Excel, en documento_empresa).

  version        correlativo por empresa: sube cuando cambia la huella respecto de la emisión anterior.
  codigo         CIA-ROPA-AAAA-NNNNNN-D (dígito verificador módulo 11 sobre el id): lo calcula el caso de
                 uso apenas conoce el id (app/application/ropa/informe.py: codigo()).
  documento_*    si la empresa elimina el archivo desde "Mis documentos", queda en NULL (ON DELETE SET NULL).

En PostgreSQL un trigger impide cambiar lo que identifica a una emisión (código, versión, huella, partes y
fecha) y borrarla: solo pueden quedar en NULL sus documentos.
"""
import json
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.cifrado_columnas import TextoCifradoRopa
from app.core.database import Base


class RopaDatos(Base):
    __tablename__ = "ropa_datos"
    __table_args__ = (UniqueConstraint("empresa_id", name="uq_ropa_datos_empresa"),)

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False)
    # JSON {direccion, correo, telefono, tiene_dpo, dpo_cargo, dpo_correo, mandantes: {clave: {...}}},
    # cifrado en reposo (subclave "ropa"): son datos de contacto (app/domain/ropa/datos.py)
    contenido: Mapped[str] = mapped_column("contenido", TextoCifradoRopa, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)
    actualizado_por_usuario_id: Mapped[int | None] = mapped_column(
        "actualizado_por_usuario_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)

    def como_dict(self) -> dict:
        try:
            datos = json.loads(self.contenido or "{}")
        except (TypeError, ValueError):       # ilegible (¿cambió la clave?): se vuelven a pedir
            datos = {}
        return datos if isinstance(datos, dict) else {}

    def guardar(self, datos: dict) -> None:
        self.contenido = json.dumps(datos, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class RopaInforme(Base):
    __tablename__ = "ropa_informe"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_ropa_informe_codigo"),
        CheckConstraint("version >= 1", name="ck_ropa_informe_version"),
        CheckConstraint("actividades >= 0", name="ck_ropa_informe_actividades"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    # NULL solo un instante: el código se calcula con el id recién asignado (misma transacción)
    codigo: Mapped[str | None] = mapped_column("codigo", String(30), nullable=True)
    version: Mapped[int] = mapped_column("version", Integer, nullable=False)
    huella: Mapped[str] = mapped_column("huella", String(64), nullable=False)
    # ["responsable", "encargado"]: las partes que trae el informe
    partes: Mapped[list] = mapped_column("partes", JSON, nullable=False, default=list)
    actividades: Mapped[int] = mapped_column("actividades", Integer, nullable=False)
    # Conteos: {responsable, encargado, organizaciones, transferencias}
    resumen: Mapped[dict] = mapped_column("resumen", JSON, nullable=False, default=dict)
    # Versión de cada actividad incluida: [{id, version, huella}]
    versiones: Mapped[list] = mapped_column("versiones", JSON, nullable=False, default=list)
    aviso_version: Mapped[str] = mapped_column("aviso_version", String(30), nullable=False)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    documento_pdf_id: Mapped[int | None] = mapped_column(
        "documento_pdf_id", Integer, ForeignKey("documento_empresa.id", ondelete="SET NULL"), nullable=True)
    documento_xlsx_id: Mapped[int | None] = mapped_column(
        "documento_xlsx_id", Integer, ForeignKey("documento_empresa.id", ondelete="SET NULL"), nullable=True)
