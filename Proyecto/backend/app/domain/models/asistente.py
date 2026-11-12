"""
HU-39 · Asistente de IA para armar el mapa de datos, el RAT y los informes.

  asistente_sesion     una entrevista guiada por áreas (personas, clientes, proveedores, marketing, TI y
                       uso de IA). Guarda en qué pregunta del banco va (app/application/asistente/banco.py).
  asistente_mensaje    cada turno de la entrevista. SOLO texto anonimizado: el mismo que vio el LLM (las
                       preguntas son del banco y no tienen datos). Un mensaje bloqueado no guarda su texto.
  asistente_documento  un documento que subió la empresa (política, contrato con proveedor, aviso). El
                       archivo NO se guarda: se lee en memoria, se extrae el texto (HU-17), se revisa con el
                       detector (HU-33) y el NER, y solo quedan sus metadatos y su huella SHA-256.
  asistente_propuesta  lo que propuso la IA (o el modo sin IA) y la decisión del usuario: Human-in-the-Loop.
                       Nada entra al mapa ni al RAT sin que el usuario la acepte (tal cual o editada). Lleva el
                       modelo, la versión del prompt y la traza de la llamada (llamadas_llm.traza_id).

En PostgreSQL un trigger impide modificar una propuesta ya decidida (aceptada, editada o descartada) y
borrar propuestas: es la prueba de qué sugirió la IA y qué decidió la persona.
"""
from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

AREAS = ("personas", "clientes", "proveedores", "marketing", "ti", "ia")
ESTADOS_SESION = ("activa", "cerrada")
ROLES_MENSAJE = ("asistente", "usuario")
TIPOS_ARCHIVO = ("pdf", "docx", "txt")
TIPOS_DOCUMENTO = ("politica", "contrato_proveedor", "aviso", "otro")
ESTADOS_DOCUMENTO = ("listo", "bloqueado", "ilegible", "rechazado_pii", "sin_texto", "sin_ia")
ORIGENES_PROPUESTA = ("entrevista", "documento", "sin_ia")
TIPOS_PROPUESTA = ("elemento", "flujo", "actividad")
ESTADOS_PROPUESTA = ("sugerida", "aceptada", "editada", "descartada", "caducada")
DECIDIDAS = ("aceptada", "editada", "descartada")
MOTIVOS_DESCARTE = ("no_aplica", "incorrecta", "duplicada", "otro")
CONFIANZAS = ("alta", "media", "baja")


def _en(valores) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


class AsistenteSesion(Base):
    __tablename__ = "asistente_sesion"
    __table_args__ = (
        CheckConstraint(f"area_actual IN {_en(AREAS)}", name="ck_asistente_sesion_area"),
        CheckConstraint(f"estado IN {_en(ESTADOS_SESION)}", name="ck_asistente_sesion_estado"),
        CheckConstraint("paso >= 0", name="ck_asistente_sesion_paso"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    area_actual: Mapped[str] = mapped_column("area_actual", String(20), nullable=False, default="personas")
    # Índice de la pregunta del banco dentro del área actual
    paso: Mapped[int] = mapped_column("paso", Integer, nullable=False, default=0)
    areas_completadas: Mapped[list] = mapped_column("areas_completadas", JSON, nullable=False, default=list)
    estado: Mapped[str] = mapped_column("estado", String(15), nullable=False, default="activa")
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)


class AsistenteMensaje(Base):
    __tablename__ = "asistente_mensaje"
    __table_args__ = (
        CheckConstraint(f"rol IN {_en(ROLES_MENSAJE)}", name="ck_asistente_mensaje_rol"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    sesion_id: Mapped[int] = mapped_column(
        "sesion_id", Integer, ForeignKey("asistente_sesion.id", ondelete="CASCADE"), nullable=False, index=True)
    rol: Mapped[str] = mapped_column("rol", String(15), nullable=False)
    area: Mapped[str | None] = mapped_column("area", String(20), nullable=True)
    pregunta_codigo: Mapped[str | None] = mapped_column("pregunta_codigo", String(40), nullable=True)
    contenido: Mapped[str] = mapped_column("contenido", Text, nullable=False)     # anonimizado
    bloqueado: Mapped[bool] = mapped_column("bloqueado", Boolean, nullable=False, default=False)
    motivo_bloqueo: Mapped[str | None] = mapped_column("motivo_bloqueo", String(30), nullable=True)
    motivo_sin_ia: Mapped[str | None] = mapped_column("motivo_sin_ia", String(30), nullable=True)
    traza_id: Mapped[str | None] = mapped_column("traza_id", String(32), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column("prompt_version", String(40), nullable=True)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)


class AsistenteDocumento(Base):
    __tablename__ = "asistente_documento"
    __table_args__ = (
        CheckConstraint(f"tipo_archivo IN {_en(TIPOS_ARCHIVO)}", name="ck_asistente_documento_tipo_archivo"),
        CheckConstraint(f"tipo_documento IN {_en(TIPOS_DOCUMENTO)}", name="ck_asistente_documento_tipo"),
        CheckConstraint(f"estado IN {_en(ESTADOS_DOCUMENTO)}", name="ck_asistente_documento_estado"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    sesion_id: Mapped[int | None] = mapped_column(
        "sesion_id", Integer, ForeignKey("asistente_sesion.id", ondelete="SET NULL"), nullable=True)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    nombre_archivo: Mapped[str] = mapped_column("nombre_archivo", String(255), nullable=False)  # anonimizado
    tipo_archivo: Mapped[str] = mapped_column("tipo_archivo", String(5), nullable=False)
    tipo_documento: Mapped[str] = mapped_column("tipo_documento", String(25), nullable=False, default="otro")
    huella_sha256: Mapped[str] = mapped_column("huella_sha256", String(64), nullable=False)
    estado: Mapped[str] = mapped_column("estado", String(20), nullable=False)
    regla_detector: Mapped[str | None] = mapped_column("regla_detector", String(60), nullable=True)
    lineas_omitidas: Mapped[int] = mapped_column("lineas_omitidas", Integer, nullable=False, default=0)
    pasajes_total: Mapped[int | None] = mapped_column("pasajes_total", Integer, nullable=True)
    pasajes_usados: Mapped[int | None] = mapped_column("pasajes_usados", Integer, nullable=True)
    entidades_anonimizadas: Mapped[int] = mapped_column("entidades_anonimizadas", Integer, nullable=False, default=0)
    motivo_sin_ia: Mapped[str | None] = mapped_column("motivo_sin_ia", String(30), nullable=True)
    traza_id: Mapped[str | None] = mapped_column("traza_id", String(32), nullable=True)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)


class AsistentePropuesta(Base):
    __tablename__ = "asistente_propuesta"
    __table_args__ = (
        CheckConstraint(f"origen IN {_en(ORIGENES_PROPUESTA)}", name="ck_asistente_propuesta_origen"),
        CheckConstraint(f"tipo IN {_en(TIPOS_PROPUESTA)}", name="ck_asistente_propuesta_tipo"),
        CheckConstraint(f"estado IN {_en(ESTADOS_PROPUESTA)}", name="ck_asistente_propuesta_estado"),
        CheckConstraint(f"confianza IN {_en(CONFIANZAS)}", name="ck_asistente_propuesta_confianza"),
        CheckConstraint(f"motivo_descarte IS NULL OR motivo_descarte IN {_en(MOTIVOS_DESCARTE)}",
                        name="ck_asistente_propuesta_motivo"),
        # Una propuesta aceptada o editada siempre sabe qué creó
        CheckConstraint("estado NOT IN ('aceptada', 'editada') OR entidad_destino_id IS NOT NULL",
                        name="ck_asistente_propuesta_destino"),
        UniqueConstraint("empresa_id", "clave", name="uq_asistente_propuesta_clave"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    sesion_id: Mapped[int | None] = mapped_column(
        "sesion_id", Integer, ForeignKey("asistente_sesion.id", ondelete="SET NULL"), nullable=True)
    documento_id: Mapped[int | None] = mapped_column(
        "documento_id", Integer, ForeignKey("asistente_documento.id", ondelete="SET NULL"), nullable=True)
    origen: Mapped[str] = mapped_column("origen", String(15), nullable=False)
    area: Mapped[str | None] = mapped_column("area", String(20), nullable=True)
    tipo: Mapped[str] = mapped_column("tipo", String(15), nullable=False)
    # Clave única en la empresa: los flujos y actividades propuestos se refieren a otras propuestas
    # con "nuevo:<clave>" (y a lo que ya está en el mapa con "id:<n>")
    clave: Mapped[str] = mapped_column("clave", String(60), nullable=False)
    estado: Mapped[str] = mapped_column("estado", String(15), nullable=False, default="sugerida")
    payload_propuesto: Mapped[dict] = mapped_column("payload_propuesto", JSON, nullable=False)
    payload_final: Mapped[dict | None] = mapped_column("payload_final", JSON, nullable=True)
    campos_editados: Mapped[list | None] = mapped_column("campos_editados", JSON, nullable=True)
    explicaciones: Mapped[dict] = mapped_column("explicaciones", JSON, nullable=False, default=dict)
    inconsistencias: Mapped[list] = mapped_column("inconsistencias", JSON, nullable=False, default=list)
    riesgo_nivel: Mapped[str | None] = mapped_column("riesgo_nivel", String(10), nullable=True)
    confianza: Mapped[str] = mapped_column("confianza", String(10), nullable=False, default="media")
    # Metadatos de IA (AC4). En el modo sin IA: modelo "sin_ia" y la versión del banco de preguntas.
    modelo: Mapped[str] = mapped_column("modelo", String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column("prompt_version", String(40), nullable=False)
    traza_id: Mapped[str | None] = mapped_column("traza_id", String(32), nullable=True)
    version_mapa_base: Mapped[int] = mapped_column("version_mapa_base", Integer, nullable=False, default=0)
    entidad_destino: Mapped[str | None] = mapped_column("entidad_destino", String(20), nullable=True)
    entidad_destino_id: Mapped[int | None] = mapped_column("entidad_destino_id", Integer, nullable=True)
    decidido_por: Mapped[int | None] = mapped_column(
        "decidido_por", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    fecha_decision: Mapped[datetime | None] = mapped_column("fecha_decision", DateTime, nullable=True)
    motivo_descarte: Mapped[str | None] = mapped_column("motivo_descarte", String(20), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
