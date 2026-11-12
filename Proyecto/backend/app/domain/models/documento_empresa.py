"""
HU-29: documentos generados que la empresa cliente guarda en "Mis documentos".

Una fila por archivo GUARDADO por el sistema para la empresa:

  informe_pdf   el informe de brechas de una evaluación (HU-11/HU-12) tal como estaba al
                generarlo. Se archiva al completar una reevaluación de la empresa o cuando
                el usuario lo pide desde "Mis evaluaciones".
  borrador      PDF de un borrador de cumplimiento CONSOLIDADO (HU-16). El borrador en revisión
                vive en borrador_documento; al consolidarlo, app/application/use_cases/borradores.py
                lo guarda aquí con guardar_documento() y aparece en "Mis documentos".
  rat_pdf       HU-36: informe PDF del Registro de Actividades de Tratamiento (una emisión de
  rat_xlsx      rat_informe guarda los dos formatos con el mismo código verificable).

Las evidencias (tabla evidencias) y las constancias (avance_formativo) NO se copian aquí:
"Mis documentos" las lee de su propia tabla para no duplicar archivos.

El archivo vive en STORAGE_DIR cifrado en reposo (Fernet, subclave "documentos" de
ENTITY_MAP_KEY) con un nombre UUID; `nombre` es el nombre de descarga, que arma el sistema
(nunca lo escribe el usuario). Eliminar borra la fila y el archivo; lo que queda es el
registro en la bitácora de auditoría (HU-09), que no lleva datos personales.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TIPO_INFORME = "informe_pdf"
TIPO_BORRADOR = "borrador"
TIPO_RAT_PDF = "rat_pdf"        # HU-36
TIPO_RAT_XLSX = "rat_xlsx"      # HU-36
TIPOS_RAT = (TIPO_RAT_PDF, TIPO_RAT_XLSX)
TIPOS_DOCUMENTO = (TIPO_INFORME, TIPO_BORRADOR, *TIPOS_RAT)


class DocumentoEmpresa(Base):
    __tablename__ = "documento_empresa"
    __table_args__ = (
        CheckConstraint("tipo IN (" + ", ".join(f"'{t}'" for t in TIPOS_DOCUMENTO) + ")",
                        name="ck_documento_empresa_tipo"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    # Evaluación de la que sale (informe) o a la que se refiere (borrador); puede faltar.
    evaluacion_id: Mapped[int | None] = mapped_column(
        "evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=True, index=True
    )
    tipo: Mapped[str] = mapped_column("tipo", String(20), nullable=False)
    # Nombre de descarga generado por el sistema: [A-Za-z0-9_.-] (sin datos personales)
    nombre: Mapped[str] = mapped_column("nombre", String(150), nullable=False)
    storage_path: Mapped[str] = mapped_column("storage_path", String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column("mime_type", String(100), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column("tamano_bytes", Integer, nullable=False)
    # SHA-256 del contenido en claro: detecta un archivo alterado o corrupto al descargarlo
    hash_contenido: Mapped[str] = mapped_column("hash_contenido", String(64), nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    # Usuario definitivo que lo generó (NULL si lo generó el sistema, p. ej. al completar)
    creado_por_usuario_id: Mapped[int | None] = mapped_column(
        "creado_por_usuario_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True
    )
