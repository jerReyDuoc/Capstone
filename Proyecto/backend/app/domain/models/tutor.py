"""
HU-15 · Conversaciones del Agente IA Tutor.

  conversacion_tutor   una conversación de la empresa (un usuario por empresa, HU-27) con el
                       tutor, atada a la evaluación más reciente que tenía la empresa al
                       abrirla. Si llega una evaluación más nueva la conversación queda de
                       solo lectura (el contexto ya no es el vigente) y se abre otra.
  mensaje_tutor        cada mensaje, SOLO con texto anonimizado: el del usuario es el mismo
                       que salió hacia el LLM tras el motor NER (HU-06) y el del tutor se
                       vuelve a pasar por el anonimizador antes de guardarse. Un mensaje
                       bloqueado por prompt injection no guarda el texto (queda el evento
                       de seguridad, con su extracto anonimizado).

Conservación (decisión del PO, 28-oct): se borran con la supresión ARCOP del usuario
definitivo y por retención a los TUTOR_RETENCION_DIAS (30) días sin actividad.
"""
from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

NIVELES_TUTOR = ("Inicial", "Intermedio", "Avanzado")


class RolMensajeTutor(str, Enum):
    USUARIO = "usuario"
    TUTOR = "tutor"


class TipoMensajeTutor(str, Enum):
    PREGUNTA = "pregunta"                  # mensaje del usuario
    EXPLICACION = "explicacion"
    PLAN_ACCION = "plan_accion"
    ORIENTACION = "orientacion"
    FUERA_DE_ALCANCE = "fuera_de_alcance"
    BLOQUEADO = "bloqueado"                # prompt injection: no se llamó al LLM

    @classmethod
    def valores(cls) -> list[str]:
        return [t.value for t in cls]


def _en(valores) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


class ConversacionTutor(Base):
    __tablename__ = "conversacion_tutor"
    __table_args__ = (
        CheckConstraint(f"nivel IN {_en(NIVELES_TUTOR)}", name="ck_conversacion_tutor_nivel"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    usuario_definitivo_id: Mapped[int] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=False, index=True)
    evaluacion_id: Mapped[int] = mapped_column("evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=False)
    # Módulo formativo desde el que se abrió (fija el nivel por defecto); NULL = panel general
    ruta_formativa_id: Mapped[int | None] = mapped_column(
        "ruta_formativa_id", Integer, ForeignKey("ruta_formativa.id"), nullable=True)
    nivel: Mapped[str] = mapped_column("nivel", String(12), nullable=False)
    # Primeras palabras del primer mensaje, ya anonimizadas
    titulo: Mapped[str | None] = mapped_column("titulo", String(120), nullable=True)
    huella_contexto: Mapped[str | None] = mapped_column("huella_contexto", String(32), nullable=True)
    mensajes_total: Mapped[int] = mapped_column("mensajes_total", Integer, nullable=False, default=0)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_ultimo_mensaje: Mapped[datetime] = mapped_column("fecha_ultimo_mensaje", DateTime, nullable=False, index=True)


class MensajeTutor(Base):
    __tablename__ = "mensaje_tutor"
    __table_args__ = (
        CheckConstraint(f"rol IN {_en(r.value for r in RolMensajeTutor)}", name="ck_mensaje_tutor_rol"),
        CheckConstraint(f"tipo IN {_en(TipoMensajeTutor.valores())}", name="ck_mensaje_tutor_tipo"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    conversacion_id: Mapped[int] = mapped_column(
        "conversacion_tutor_id", Integer, ForeignKey("conversacion_tutor.id", ondelete="CASCADE"),
        nullable=False, index=True)
    rol: Mapped[str] = mapped_column("rol", String(10), nullable=False)
    tipo: Mapped[str] = mapped_column("tipo", String(20), nullable=False)
    # Texto ANONIMIZADO (nunca el original)
    contenido: Mapped[str] = mapped_column("contenido", Text, nullable=False)
    nivel: Mapped[str | None] = mapped_column("nivel", String(12), nullable=True)
    # Respuesta estructurada del tutor: pasos, brechas_referenciadas, referencias_normativas, sugerencias
    datos: Mapped[dict | None] = mapped_column("datos", JSON, nullable=True)
    bloqueado: Mapped[bool] = mapped_column("bloqueado", Boolean, nullable=False, default=False)
    motivo_bloqueo: Mapped[str | None] = mapped_column("motivo_bloqueo", String(30), nullable=True)
    # Une el mensaje con su llamada al LLM (llamadas_llm.traza_id) y su sanitización
    traza_id: Mapped[str | None] = mapped_column("traza_id", String(32), nullable=True, index=True)
    prompt_version: Mapped[str | None] = mapped_column("prompt_version", String(60), nullable=True)
    advertencias: Mapped[list | None] = mapped_column("advertencias", JSON, nullable=True)
    huella_contexto: Mapped[str | None] = mapped_column("huella_contexto", String(32), nullable=True)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
