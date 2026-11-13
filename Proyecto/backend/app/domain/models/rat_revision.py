"""
HU-40 · Revisión interna del registro de actividades (modo de auditoría interna del cliente).

El mismo usuario definitivo revisa el mapa de datos, el RAT y sus informes con una lista de verificación y
deja constancia. No hay roles ni cuentas nuevas.

  rat_revision            una revisión de la empresa. Mientras está "en_curso" guarda lo que el usuario fue
                          verificando (verificaciones: por elemento revisado, con la huella que tenía cuando lo
                          verificó: si cambia, la verificación queda desactualizada). Al quedar "revisada" fija
                          la versión del RAT, su huella, la fecha, el nombre y cargo de quien revisó y una
                          copia de la lista de verificación. Desde ahí es INMUTABLE (trigger en PostgreSQL):
                          solo se le asigna una vez el informe del RAT emitido con la marca.
  rat_observacion         observaciones por actividad, elemento o flujo del mapa (o del registro en general).
                          Se cierran al corregir; con alguna abierta la versión no se puede marcar revisada.
                          No se borran y lo que se observó no cambia (trigger).
  rat_revision_config     plazo de la revisión periódica de la empresa (meses), aviso previo y si quiere el
                          recordatorio por correo; y cuándo se le recordó por última vez.
  rat_paquete_evidencia   cada paquete de evidencia (ZIP) exportado: código verificable y SHA-256 (trigger:
                          inmutable).

Datos personales: el nombre y el cargo de quien revisa (los pone la persona al marcar, para la constancia).
Las observaciones describen el registro, no a personas: se rechazan correos, RUT y teléfonos. El audit_log
solo lleva ids, códigos y conteos.
"""
from datetime import datetime

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

EN_CURSO, REVISADA = "en_curso", "revisada"
ESTADOS_REVISION = (EN_CURSO, REVISADA)
ABIERTA, CERRADA = "abierta", "cerrada"
PRIORIDADES = ("alta", "media", "baja")
TIPOS_OBJETO = ("actividad", "elemento", "flujo", "registro")


def _en(valores) -> str:
    return "(" + ", ".join(f"'{v}'" for v in valores) + ")"


class RatRevision(Base):
    __tablename__ = "rat_revision"
    __table_args__ = (
        UniqueConstraint("empresa_id", "numero", name="uq_rat_revision_numero"),
        CheckConstraint(f"estado IN {_en(ESTADOS_REVISION)}", name="ck_rat_revision_estado"),
        CheckConstraint("numero >= 1", name="ck_rat_revision_numero"),
        # Una revisada siempre dice qué versión, con qué huella, cuándo y quién
        CheckConstraint("estado <> 'revisada' OR (version_rat IS NOT NULL AND huella IS NOT NULL "
                        "AND fecha_revision IS NOT NULL AND revisor_nombre IS NOT NULL)",
                        name="ck_rat_revision_revisada"),
        # Una sola revisión en curso por empresa
        Index("ux_rat_revision_en_curso", "empresa_id", unique=True,
              postgresql_where=text("estado = 'en_curso'"), sqlite_where=text("estado = 'en_curso'")),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    numero: Mapped[int] = mapped_column("numero", Integer, nullable=False)
    estado: Mapped[str] = mapped_column("estado", String(10), nullable=False, default=EN_CURSO)
    fecha_inicio: Mapped[datetime] = mapped_column("fecha_inicio", DateTime, nullable=False)
    iniciada_por_id: Mapped[int | None] = mapped_column(
        "iniciada_por_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    # {clave_objeto: {"huella": str, "items": {criterio: {"estado": "verificado"|"aceptado", "nota", "fecha"}}}}
    verificaciones: Mapped[dict] = mapped_column("verificaciones", JSON, nullable=False, default=dict)
    # Lo que fija la marca de revisada
    fecha_revision: Mapped[datetime | None] = mapped_column("fecha_revision", DateTime, nullable=True)
    revisado_por_id: Mapped[int | None] = mapped_column(
        "revisado_por_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    revisor_nombre: Mapped[str | None] = mapped_column("revisor_nombre", String(120), nullable=True)
    revisor_cargo: Mapped[str | None] = mapped_column("revisor_cargo", String(120), nullable=True)
    conclusion: Mapped[str | None] = mapped_column("conclusion", Text, nullable=True)
    version_rat: Mapped[int | None] = mapped_column("version_rat", Integer, nullable=True)
    huella: Mapped[str | None] = mapped_column("huella", String(64), nullable=True)
    version_mapa: Mapped[int | None] = mapped_column("version_mapa", Integer, nullable=True)
    # Cifras de la revisión y copia de la lista de verificación al marcarla (para la constancia y el paquete)
    resumen: Mapped[dict] = mapped_column("resumen", JSON, nullable=False, default=dict)
    lista: Mapped[list] = mapped_column("lista", JSON, nullable=False, default=list)
    # Informe del RAT emitido con la marca (se asigna una sola vez, después de marcar). Sin llave foránea para no
    # crear un ciclo con rat_informe.revision_id (como rat_actividad.version_vigente).
    informe_id: Mapped[int | None] = mapped_column("informe_id", Integer, nullable=True)


class RatObservacion(Base):
    __tablename__ = "rat_observacion"
    __table_args__ = (
        UniqueConstraint("empresa_id", "numero", name="uq_rat_observacion_numero"),
        CheckConstraint(f"estado IN {_en((ABIERTA, CERRADA))}", name="ck_rat_observacion_estado"),
        CheckConstraint(f"prioridad IN {_en(PRIORIDADES)}", name="ck_rat_observacion_prioridad"),
        CheckConstraint(f"objeto_tipo IN {_en(TIPOS_OBJETO)}", name="ck_rat_observacion_objeto"),
        CheckConstraint("estado <> 'cerrada' OR (fecha_cierre IS NOT NULL AND nota_cierre IS NOT NULL)",
                        name="ck_rat_observacion_cierre"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    revision_id: Mapped[int] = mapped_column("revision_id", Integer, ForeignKey("rat_revision.id"), nullable=False,
                                             index=True)
    numero: Mapped[int] = mapped_column("numero", Integer, nullable=False)
    objeto_tipo: Mapped[str] = mapped_column("objeto_tipo", String(10), nullable=False)
    objeto_id: Mapped[int | None] = mapped_column("objeto_id", Integer, nullable=True)
    objeto_clave: Mapped[str] = mapped_column("objeto_clave", String(40), nullable=False)
    # Nombre del elemento al observarlo (si después se renombra o elimina, la observación sigue legible)
    objeto_nombre: Mapped[str] = mapped_column("objeto_nombre", String(200), nullable=False)
    criterio: Mapped[str | None] = mapped_column("criterio", String(40), nullable=True)
    prioridad: Mapped[str] = mapped_column("prioridad", String(10), nullable=False, default="media")
    texto: Mapped[str] = mapped_column("texto", Text, nullable=False)
    estado: Mapped[str] = mapped_column("estado", String(10), nullable=False, default=ABIERTA)
    fecha_apertura: Mapped[datetime] = mapped_column("fecha_apertura", DateTime, nullable=False)
    abierta_por_id: Mapped[int | None] = mapped_column(
        "abierta_por_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    huella_apertura: Mapped[str | None] = mapped_column("huella_apertura", String(64), nullable=True)
    fecha_cierre: Mapped[datetime | None] = mapped_column("fecha_cierre", DateTime, nullable=True)
    cerrada_por_id: Mapped[int | None] = mapped_column(
        "cerrada_por_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
    nota_cierre: Mapped[str | None] = mapped_column("nota_cierre", Text, nullable=True)
    huella_cierre: Mapped[str | None] = mapped_column("huella_cierre", String(64), nullable=True)
    # ¿Cambió el elemento observado entre la apertura y el cierre? (corregido o solo explicado)
    objeto_cambio: Mapped[bool | None] = mapped_column("objeto_cambio", Boolean, nullable=True)
    reaperturas: Mapped[int] = mapped_column("reaperturas", Integer, nullable=False, default=0)


class RatRevisionConfig(Base):
    __tablename__ = "rat_revision_config"
    __table_args__ = (
        CheckConstraint("plazo_meses BETWEEN 1 AND 36", name="ck_rat_revision_config_plazo"),
        CheckConstraint("aviso_dias BETWEEN 0 AND 90", name="ck_rat_revision_config_aviso"),
    )

    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), primary_key=True)
    plazo_meses: Mapped[int] = mapped_column("plazo_meses", Integer, nullable=False, default=12)
    aviso_dias: Mapped[int] = mapped_column("aviso_dias", Integer, nullable=False, default=30)
    recordatorio_correo: Mapped[bool] = mapped_column("recordatorio_correo", Boolean, nullable=False, default=True)
    ultimo_recordatorio: Mapped[datetime | None] = mapped_column("ultimo_recordatorio", DateTime, nullable=True)
    # Etapa a la que corresponde el último recordatorio ("por_vencer:2027-11-13" o "vencida:2027-11-13")
    etapa_recordatorio: Mapped[str | None] = mapped_column("etapa_recordatorio", String(40), nullable=True)
    fecha_actualizacion: Mapped[datetime] = mapped_column("fecha_actualizacion", DateTime, nullable=False)


class RatPaqueteEvidencia(Base):
    __tablename__ = "rat_paquete_evidencia"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_rat_paquete_codigo"),
        UniqueConstraint("sha256", name="uq_rat_paquete_sha256"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column("empresa_id", Integer, ForeignKey("empresa.id"), nullable=False, index=True)
    revision_id: Mapped[int] = mapped_column("revision_id", Integer, ForeignKey("rat_revision.id"), nullable=False)
    codigo: Mapped[str | None] = mapped_column("codigo", String(30), nullable=True)
    sha256: Mapped[str] = mapped_column("sha256", String(64), nullable=False)
    huella_manifiesto: Mapped[str] = mapped_column("huella_manifiesto", String(64), nullable=False)
    archivos: Mapped[int] = mapped_column("archivos", Integer, nullable=False)
    tamano_bytes: Mapped[int] = mapped_column("tamano_bytes", Integer, nullable=False)
    fecha: Mapped[datetime] = mapped_column("fecha", DateTime, nullable=False)
    usuario_definitivo_id: Mapped[int | None] = mapped_column(
        "usuario_definitivo_id", Integer, ForeignKey("usuario_definitivo.id"), nullable=True)
