from datetime import datetime
from sqlalchemy import Integer, String, Text, Boolean, DateTime, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class LlamadaLLM(Base):
    """
    Métrica de cada ejecución de la capa de IA (exitosa o fallida).
    Base para: tasa de error, latencia, consumo de tokens, costo y precisión
    del modelo (comparando `clasificacion` con la revisión humana).
    Nunca contiene texto del usuario.
    """
    __tablename__ = "llamadas_llm"

    id_llamada: Mapped[int] = mapped_column("id_llamada", Integer, primary_key=True)
    traza_id: Mapped[str] = mapped_column("traza_id", String(32), nullable=False, index=True)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False, index=True)

    tarea: Mapped[str] = mapped_column("tarea", String(40), nullable=False)
    proveedor: Mapped[str] = mapped_column("proveedor", String(30), nullable=False)
    modelo: Mapped[str] = mapped_column("modelo", String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column("prompt_version", String(60), nullable=False)

    exito: Mapped[bool] = mapped_column("exito", Boolean, nullable=False)
    tipo_error: Mapped[str | None] = mapped_column("tipo_error", String(30), nullable=True)
    detalle_error: Mapped[str | None] = mapped_column("detalle_error", Text, nullable=True)

    tokens_entrada: Mapped[int | None] = mapped_column("tokens_entrada", Integer, nullable=True)
    tokens_salida: Mapped[int | None] = mapped_column("tokens_salida", Integer, nullable=True)
    costo_estimado_usd: Mapped[float | None] = mapped_column("costo_estimado_usd", Float, nullable=True)
    latencia_ms: Mapped[float | None] = mapped_column("latencia_ms", Float, nullable=True)

    sanitizado: Mapped[bool] = mapped_column("sanitizado", Boolean, nullable=False, default=True)
    entidades_anonimizadas: Mapped[int] = mapped_column("entidades_anonimizadas", Integer, nullable=False, default=0)

    clasificacion: Mapped[str | None] = mapped_column("clasificacion", String(25), nullable=True)
    confianza: Mapped[float | None] = mapped_column("confianza", Float, nullable=True)
    advertencias: Mapped[list | None] = mapped_column("advertencias", JSON, nullable=True)

    evaluacion_id: Mapped[int | None] = mapped_column(
        "Evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=True
    )
    respuesta_id: Mapped[int | None] = mapped_column(
        "Respuestas_id_respuesta", Integer, ForeignKey("respuestas.id_respuesta"), nullable=True, index=True
    )
    evidencia_id: Mapped[int | None] = mapped_column(
        "Evidencias_id_evidencia", Integer, ForeignKey("evidencias.id_evidencia"), nullable=True
    )
