from datetime import date, datetime
from sqlalchemy import Integer, String, Date, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.domain.contrato import EstadoContrato, SituacionContrato, Vigencia, evaluar

_ESTADOS = ", ".join(f"'{v}'" for v in EstadoContrato.valores())
_MOTIVOS = "('no_pago', 'solicitud_cliente', 'incumplimiento', 'fin_acuerdo', 'otro')"


class Empresa(Base):
    """
    HU-27: empresa cliente que contrató el servicio pagado (cursos y tutor IA).

    La crea un administrador de Therion Labs desde el panel interno a partir de una
    solicitud de contratación (HU-31). Sus evaluaciones migradas quedan en
    evaluacion.empresa_id y su único usuario en usuario_definitivo.

    El RUT es el de la persona JURÍDICA (no es un dato personal); se guarda normalizado
    sin puntos y con guion: 76123456-7 (ver app/core/rut.py).

    HU-30: el contrato tiene un estado que fija el admin (activo, suspendido, terminado) y
    sus fechas. La situación (vigente, vencido, en plazo de gracia...) se calcula con
    `vigencia()`; las reglas están en app/domain/contrato.py.
    """
    __tablename__ = "empresa"
    __table_args__ = (
        CheckConstraint("fecha_termino_contrato >= fecha_inicio_contrato", name="ck_empresa_fechas_contrato"),
        CheckConstraint(f"estado_contrato IN ({_ESTADOS})", name="ck_empresa_estado_contrato"),
        CheckConstraint(f"motivo_suspension IS NULL OR motivo_suspension IN {_MOTIVOS}",
                        name="ck_empresa_motivo_suspension"),
        CheckConstraint(f"motivo_terminacion IS NULL OR motivo_terminacion IN {_MOTIVOS}",
                        name="ck_empresa_motivo_terminacion"),
    )

    id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    razon_social: Mapped[str] = mapped_column("razon_social", String(150), nullable=False)
    rut: Mapped[str] = mapped_column("rut", String(12), nullable=False, unique=True)
    rubro_id: Mapped[int] = mapped_column("rubro_id", Integer, ForeignKey("rubro.id"), nullable=False)
    fecha_inicio_contrato: Mapped[date] = mapped_column("fecha_inicio_contrato", Date, nullable=False)
    fecha_termino_contrato: Mapped[date] = mapped_column("fecha_termino_contrato", Date, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column("fecha_creacion", DateTime, nullable=False)
    creada_por_admin_id: Mapped[int | None] = mapped_column(
        "creada_por_admin_id", Integer, ForeignKey("usuarios_admin.id_admin"), nullable=True
    )

    # ---------------------------------------------------------------- HU-30
    estado_contrato: Mapped[str] = mapped_column(
        "estado_contrato", String(15), nullable=False,
        default=EstadoContrato.ACTIVO.value, server_default=EstadoContrato.ACTIVO.value,
    )
    fecha_suspension: Mapped[datetime | None] = mapped_column("fecha_suspension", DateTime, nullable=True)
    motivo_suspension: Mapped[str | None] = mapped_column("motivo_suspension", String(20), nullable=True)
    fecha_terminacion: Mapped[datetime | None] = mapped_column("fecha_terminacion", DateTime, nullable=True)
    motivo_terminacion: Mapped[str | None] = mapped_column("motivo_terminacion", String(20), nullable=True)
    fecha_actualizacion_contrato: Mapped[datetime | None] = mapped_column(
        "fecha_actualizacion_contrato", DateTime, nullable=True
    )

    def vigencia(self, hoy: date | None = None, gracia_dias: int | None = None) -> Vigencia:
        from app.core.config import settings

        return evaluar(
            estado=self.estado_contrato or EstadoContrato.ACTIVO.value,
            inicio=self.fecha_inicio_contrato,
            termino=self.fecha_termino_contrato,
            fecha_terminacion=self.fecha_terminacion.date() if self.fecha_terminacion else None,
            hoy=hoy or date.today(),
            gracia_dias=settings.CONTRATO_GRACIA_DIAS if gracia_dias is None else gracia_dias,
        )

    def contrato_vigente(self, hoy: date | None = None) -> bool:
        """Vigente = el servicio pagado está habilitado (HU-30: además no suspendido ni terminado)."""
        return self.vigencia(hoy).situacion is SituacionContrato.VIGENTE
