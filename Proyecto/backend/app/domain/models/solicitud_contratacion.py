from datetime import datetime
from enum import Enum
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, CheckConstraint, false as sa_false
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class EstadoSolicitudContratacion(str, Enum):
    """
    Estados de la bandeja del administrador (HU-31 criterio 3; HU-28 la integra al panel).

    nueva      -> el encuestado pidió contratar desde sus resultados.
    contactada -> el equipo comercial de Therion Labs ya habló con la persona.
    contratada -> se cerró el acuerdo comercial. Habilita la migración (HU-27).
    descartada -> no se concretó. Estado final (se borra el contacto).
    migrada    -> estado TÉCNICO que fija HU-27 al traspasar la evaluación. Final.
                  En la bandeja se muestra como "contratada" con la evaluación ya migrada.

    HU-31 renombró 'pendiente' (base de HU-27) a 'nueva' y agregó 'contactada'.
    """
    NUEVA = "nueva"
    CONTACTADA = "contactada"
    CONTRATADA = "contratada"
    MIGRADA = "migrada"
    DESCARTADA = "descartada"

    @classmethod
    def valores(cls) -> list[str]:
        return [e.value for e in cls]


class SolicitudContratacion(Base):
    """
    Solicitud de contratación del servicio pagado (HU-31; la base mínima la creó HU-27).

    La registra el encuestado desde sus resultados ("Contratar la plataforma"), para UNA
    evaluación (decisión del PO: se migra solo la evaluación de la solicitud), con DOS
    consentimientos separados, cada uno con su versión y fecha:
      1. contacto comercial  -> consentimiento_contacto_version / fecha_consentimiento_contacto
      2. traspaso a la empresa si contrata -> autoriza_migracion / consentimiento_version /
         fecha_autorizacion (nombres heredados de HU-27). Sin él, HU-27 no migra.

    Lo que HU-27 necesita y no debe cambiar:
      - evaluacion_id, autoriza_migracion y estado ('contratada' para poder migrar),
      - al migrar se borran nombre_contacto, cargo_contacto, email_contacto y telefono_contacto
        (el contacto pasa al usuario definitivo; no se duplica) y se fija empresa_id.
    """
    __tablename__ = "solicitud_contratacion"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('nueva', 'contactada', 'contratada', 'migrada', 'descartada')",
            name="ck_solicitud_contratacion_estado",
        ),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    evaluacion_id: Mapped[int] = mapped_column(
        "evaluacion_id", Integer, ForeignKey("evaluacion.id"), nullable=False, unique=True
    )
    # Contacto que dejó el usuario temporal para que Therion Labs lo llame. Se borra al migrar.
    nombre_contacto: Mapped[str | None] = mapped_column("nombre_contacto", String(120), nullable=True)
    cargo_contacto: Mapped[str | None] = mapped_column("cargo_contacto", String(80), nullable=True)
    email_contacto: Mapped[str | None] = mapped_column("email_contacto", String(100), nullable=True)
    telefono_contacto: Mapped[str | None] = mapped_column("telefono_contacto", String(30), nullable=True)
    # Empresa que declaró (obligatoria desde HU-31); la razón social oficial la ingresa el
    # admin al dar de alta la empresa (HU-27). No es dato personal y no se borra al migrar.
    razon_social_declarada: Mapped[str | None] = mapped_column("razon_social_declarada", String(150), nullable=True)
    # Consentimiento 1: contacto comercial (HU-31). NULL solo en filas anteriores a HU-31.
    consentimiento_contacto_version: Mapped[str | None] = mapped_column(
        "consentimiento_contacto_version", String(20), nullable=True)
    fecha_consentimiento_contacto: Mapped[datetime | None] = mapped_column(
        "fecha_consentimiento_contacto", DateTime, nullable=True)
    # Consentimiento 2: asociar la evaluación a la empresa si contrata (habilita HU-27).
    autoriza_migracion: Mapped[bool] = mapped_column(
        "autoriza_migracion", Boolean, nullable=False, default=False, server_default=sa_false()
    )
    consentimiento_version: Mapped[str | None] = mapped_column("consentimiento_version", String(20), nullable=True)
    fecha_autorizacion: Mapped[datetime | None] = mapped_column("fecha_autorizacion", DateTime, nullable=True)
    estado: Mapped[str] = mapped_column(
        "estado", String(20), nullable=False, index=True,
        default=EstadoSolicitudContratacion.NUEVA.value,
        server_default=EstadoSolicitudContratacion.NUEVA.value,
    )
    empresa_id: Mapped[int | None] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column("fecha_actualizacion", DateTime, nullable=True)
    fecha_migracion: Mapped[datetime | None] = mapped_column("fecha_migracion", DateTime, nullable=True)
