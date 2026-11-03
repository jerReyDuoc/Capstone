"""
HU-16 · Borradores de documentos de cumplimiento en revisión.

  borrador_documento   un borrador generado para la empresa a partir de una plantilla
                       (Política de uso de LLM, Aviso de privacidad o PIA) y de su
                       evaluación más reciente. Mientras está EN REVISIÓN el usuario lo
                       edita (Markdown) y lo descarga en Markdown o PDF (criterio 3). Al
                       CONSOLIDARLO queda de solo lectura y su PDF se guarda en "Mis
                       documentos" (documento_empresa, tipo borrador, HU-29).

  - El contenido se guarda CIFRADO (TextoCifradoBorrador, subclave "borradores"): la empresa
    escribe ahí datos de contacto reales que el documento necesita (excepción documentada,
    igual que ARCOP en HU-06). Nunca se envía al LLM: el modelo solo ve la plantilla base,
    datos de catálogo y las instrucciones sanitizadas por el NER.
  - Las instrucciones que la empresa dio al Agente IA NO se guardan (solo su huella en la
    bitácora de auditoría).
  - `version` sube en cada edición: un guardado con una versión vieja responde 409 (dos
    pestañas o dos personas editando a la vez no se pisan).
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.cifrado_columnas import TextoCifradoBorrador
from app.core.database import Base

TIPOS_BORRADOR = ("politica_llm", "aviso_privacidad", "pia")


class EstadoBorrador(str, Enum):
    EN_REVISION = "en_revision"
    CONSOLIDADO = "consolidado"

    @classmethod
    def valores(cls) -> list[str]:
        return [e.value for e in cls]


def _en(valores) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


class BorradorDocumento(Base):
    __tablename__ = "borrador_documento"
    __table_args__ = (
        CheckConstraint(f"tipo IN {_en(TIPOS_BORRADOR)}", name="ck_borrador_documento_tipo"),
        CheckConstraint(f"estado IN {_en(EstadoBorrador.valores())}", name="ck_borrador_documento_estado"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    # Evaluación cuyas brechas y puntajes se usaron (la más reciente al generarlo)
    evaluacion_id: Mapped[int | None] = mapped_column(
        "evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=True)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    tipo: Mapped[str] = mapped_column("tipo", String(30), nullable=False)
    titulo: Mapped[str] = mapped_column("titulo", String(150), nullable=False)   # el de la plantilla
    estado: Mapped[str] = mapped_column("estado", String(20), nullable=False, default=EstadoBorrador.EN_REVISION.value)
    version: Mapped[int] = mapped_column("version", Integer, nullable=False, default=1)
    contenido: Mapped[str] = mapped_column("contenido", TextoCifradoBorrador, nullable=False)   # Markdown
    adaptado_ia: Mapped[bool] = mapped_column("adaptado_ia", Boolean, nullable=False, default=False)
    prompt_version: Mapped[str | None] = mapped_column("prompt_version", String(40), nullable=True)
    traza_id: Mapped[str | None] = mapped_column("traza_id", String(32), nullable=True)
    version_plantillas: Mapped[str] = mapped_column("version_plantillas", String(20), nullable=False)
    huella_contexto: Mapped[str | None] = mapped_column("huella_contexto", String(32), nullable=True)
    # Notas de revisión del Agente IA (sobre texto ya anonimizado) y advertencias de la generación
    notas: Mapped[list | None] = mapped_column("notas", JSON, nullable=True)
    advertencias: Mapped[list | None] = mapped_column("advertencias", JSON, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)
    fecha_consolidacion: Mapped[datetime | None] = mapped_column("fecha_consolidacion", DateTime, nullable=True)
    # PDF consolidado en "Mis documentos" (NULL si aún no se consolida o si el usuario lo borró)
    documento_id: Mapped[int | None] = mapped_column(
        "documento_id", Integer, ForeignKey("documento_empresa.id", ondelete="SET NULL"), nullable=True)

    @property
    def editable(self) -> bool:
        return self.estado == EstadoBorrador.EN_REVISION.value
