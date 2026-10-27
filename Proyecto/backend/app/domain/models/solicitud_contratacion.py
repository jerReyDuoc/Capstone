from datetime import datetime
from enum import Enum
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, CheckConstraint, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class EstadoSolicitudContratacion(str, Enum):
    """
    pendiente  -> el usuario temporal pidió contratar desde el final de su evaluación.
    contratada -> Therion Labs cerró el acuerdo comercial (lo marca un admin).
    migrada    -> la evaluación ya pasó a la empresa (HU-27). Estado final.
    descartada -> no se concretó. Estado final.
    """
    PENDIENTE = "pendiente"
    CONTRATADA = "contratada"
    MIGRADA = "migrada"
    DESCARTADA = "descartada"

    @classmethod
    def valores(cls) -> list[str]:
        return [e.value for e in cls]


class SolicitudContratacion(Base):
    """
    Solicitud de contratación del servicio pagado (BASE MÍNIMA de HU-31, creada en HU-27).

    La registra el usuario temporal al terminar su autodiagnóstico, para UNA evaluación
    (decisión del PO: se migra solo la evaluación de la solicitud), y en ella autoriza
    expresamente que esa evaluación se traspase a la empresa si contrata.

    HU-31 puede ampliarla (textos de consentimiento definitivos, notificaciones,
    seguimiento comercial). Lo que HU-27 necesita y no debe cambiar:
      - evaluacion_id, autoriza_migracion y estado ('contratada' para poder migrar),
      - al migrar se borran nombre_contacto, email_contacto y telefono_contacto
        (el contacto pasa al usuario definitivo; no se duplica) y se fija empresa_id.
    """
    __tablename__ = "solicitud_contratacion"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('pendiente', 'contratada', 'migrada', 'descartada')",
            name="ck_solicitud_contratacion_estado",
        ),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    evaluacion_id: Mapped[int] = mapped_column(
        "evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=False, unique=True
    )
    # Contacto que dejó el usuario temporal para que Therion Labs lo llame. Se borra al migrar.
    nombre_contacto: Mapped[str | None] = mapped_column("nombre_contacto", String(120), nullable=True)
    email_contacto: Mapped[str | None] = mapped_column("email_contacto", String(100), nullable=True)
    telefono_contacto: Mapped[str | None] = mapped_column("telefono_contacto", String(30), nullable=True)
    # Lo que el usuario declaró; la razón social oficial la ingresa el admin en la empresa.
    razon_social_declarada: Mapped[str | None] = mapped_column("razon_social_declarada", String(150), nullable=True)
    autoriza_migracion: Mapped[bool] = mapped_column(
        "autoriza_migracion", Boolean, nullable=False, default=False, server_default=sa_false()
    )
    consentimiento_version: Mapped[str | None] = mapped_column("consentimiento_version", String(20), nullable=True)
    fecha_autorizacion: Mapped[datetime | None] = mapped_column("fecha_autorizacion", DateTime, nullable=True)
    estado: Mapped[str] = mapped_column(
        "estado", String(20), nullable=False,
        default=EstadoSolicitudContratacion.PENDIENTE.value,
        server_default=EstadoSolicitudContratacion.PENDIENTE.value,
    )
    empresa_id: Mapped[int | None] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column("fecha_actualizacion", DateTime, nullable=True)
    fecha_migracion: Mapped[datetime | None] = mapped_column("fecha_migracion", DateTime, nullable=True)
