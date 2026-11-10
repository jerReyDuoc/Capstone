from datetime import datetime
from enum import Enum
from sqlalchemy import Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class OrigenEvento(str, Enum):
    JUSTIFICACION = "justificacion"
    EVIDENCIA = "evidencia"
    TUTOR = "tutor"  # HU-15: mensaje al Agente IA Tutor
    TUTOR_ANTECEDENTE = "tutor_antecedente"  # HU-18: justificación guardada con inyección (se omitió)
    BORRADOR = "borrador"  # HU-16: instrucciones de redacción de un borrador


class ResolucionEvento(str, Enum):
    """HU-22: veredicto del Oficial de Cumplimiento sobre un evento de seguridad."""
    ATAQUE_CONFIRMADO = "ataque_confirmado"   # la detección acertó
    FALSO_POSITIVO = "falso_positivo"         # el texto era legítimo: sirve para afinar las reglas

    @classmethod
    def valores(cls) -> list[str]:
        return [v.value for v in cls]


class EventoSeguridad(Base):
    """
    Registro de intentos de prompt injection detectados por la capa de seguridad.
    Lo escribe SIEMPRE el backend (nunca el LLM). Sirve como bandeja de revisión
    para el Oficial de Cumplimiento.
    """
    __tablename__ = "eventos_seguridad"

    id_evento: Mapped[int] = mapped_column("id_evento", Integer, primary_key=True)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    tipo: Mapped[str] = mapped_column("tipo", String(30), nullable=False, default="prompt_injection")
    # HU-33: identificador de la regla del detector que disparó ("manipulacion.aprueba",
    # "codificado.base64>inyeccion.ignorar_instrucciones"...). Nunca contiene texto del usuario.
    regla: Mapped[str | None] = mapped_column("regla", String(80), nullable=True, index=True)
    origen: Mapped[str] = mapped_column("origen", String(20), nullable=False)

    evaluacion_id: Mapped[int | None] = mapped_column(
        "Evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=True
    )
    matriz_control_id: Mapped[int | None] = mapped_column(
        "Matriz_controles_id_control", Integer, ForeignKey("matriz_controles.id_control"), nullable=True
    )
    respuesta_id: Mapped[int | None] = mapped_column(
        "Respuestas_id_respuesta", Integer, ForeignKey("respuestas.id_respuesta"), nullable=True
    )
    evidencia_id: Mapped[int | None] = mapped_column(
        "Evidencias_id_evidencia", Integer, ForeignKey("evidencias.id_evidencia"), nullable=True
    )

    # Extracto YA ANONIMIZADO y truncado (nunca se guarda PII en claro aquí)
    extracto: Mapped[str | None] = mapped_column("extracto", Text, nullable=True)
    hash_texto: Mapped[str] = mapped_column("hash_texto", String(64), nullable=False, index=True)
    revisado: Mapped[bool] = mapped_column("revisado", Boolean, nullable=False, default=False)

    # HU-22: resultado de la revisión (NULL en los eventos revisados antes de HU-22)
    resolucion: Mapped[str | None] = mapped_column("resolucion", String(20), nullable=True)
    comentario_revision: Mapped[str | None] = mapped_column("comentario_revision", Text, nullable=True)
    fecha_revision: Mapped[datetime | None] = mapped_column("fecha_revision", DateTime, nullable=True)
    revisor_admin_id: Mapped[int | None] = mapped_column(
        "revisor_admin_id", Integer, ForeignKey("usuarios_admin.id_admin"), nullable=True
    )
