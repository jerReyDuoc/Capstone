"""
HU-36 · Emisiones del informe del Registro de Actividades de Tratamiento (RAT).

Una fila por cada informe que la empresa emite. Guarda lo que identifica al informe (criterio 2):
código verificable, versión del RAT, fecha de emisión, si salió como borrador (criterio 4) y la huella
de lo que afirma el registro; además el resumen que se mostró y los documentos que quedaron en
"Mis documentos" (criterio 3: el PDF y la planilla XLSX, en documento_empresa).

  version_rat   correlativo por empresa: sube cuando cambia la huella respecto de la emisión anterior.
                Dos emisiones con la misma versión afirman lo mismo.
  codigo        CIA-REG-AAAA-NNNNNN-D (dígito verificador módulo 11 sobre el id): lo calcula el caso
                de uso apenas conoce el id (app/application/rat/informe.py: codigo()).
  documento_*   si la empresa elimina el archivo desde "Mis documentos", queda en NULL (ON DELETE SET
                NULL) y la emisión se sigue pudiendo verificar.

Sin datos personales: cifras, códigos y huellas. En PostgreSQL un trigger impide cambiar lo que
identifica a una emisión (código, versión, huella, borrador y fecha): solo pueden quedar en NULL sus
documentos.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RatInforme(Base):
    __tablename__ = "rat_informe"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_rat_informe_codigo"),
        CheckConstraint("version_rat >= 1", name="ck_rat_informe_version"),
        CheckConstraint("actividades >= 0", name="ck_rat_informe_actividades"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    # NULL solo un instante: el código se calcula con el id recién asignado (misma transacción)
    codigo: Mapped[str | None] = mapped_column("codigo", String(30), nullable=True)
    version_rat: Mapped[int] = mapped_column("version_rat", Integer, nullable=False)
    huella: Mapped[str] = mapped_column("huella", String(64), nullable=False)
    borrador: Mapped[bool] = mapped_column("borrador", Boolean, nullable=False)
    motivos_borrador: Mapped[list] = mapped_column("motivos_borrador", JSON, nullable=False, default=list)
    actividades: Mapped[int] = mapped_column("actividades", Integer, nullable=False)
    # Cifras del resumen ejecutivo (para listar, verificar y armar el correo sin regenerar)
    resumen: Mapped[dict] = mapped_column("resumen", JSON, nullable=False, default=dict)
    # Versión de cada actividad incluida: [{id, version, huella}] (para verificar)
    versiones: Mapped[list] = mapped_column("versiones", JSON, nullable=False, default=list)
    aviso_version: Mapped[str] = mapped_column("aviso_version", String(30), nullable=False)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    documento_pdf_id: Mapped[int | None] = mapped_column(
        "documento_pdf_id", Integer, ForeignKey("documento_empresa.id", ondelete="SET NULL"), nullable=True)
    documento_xlsx_id: Mapped[int | None] = mapped_column(
        "documento_xlsx_id", Integer, ForeignKey("documento_empresa.id", ondelete="SET NULL"), nullable=True)
