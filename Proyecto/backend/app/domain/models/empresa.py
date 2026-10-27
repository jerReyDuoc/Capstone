from datetime import date, datetime
from sqlalchemy import Integer, String, Date, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Empresa(Base):
    """
    HU-27: empresa cliente que contrató el servicio pagado (cursos y tutor IA).

    La crea un administrador de Therion Labs desde el panel interno a partir de una
    solicitud de contratación (HU-31). Sus evaluaciones migradas quedan en
    evaluacion.empresa_id y su único usuario en usuario_definitivo.

    El RUT es el de la persona JURÍDICA (no es un dato personal); se guarda normalizado
    sin puntos y con guion: 76123456-7 (ver app/core/rut.py).
    """
    __tablename__ = "empresa"
    __table_args__ = (
        CheckConstraint("fecha_termino_contrato >= fecha_inicio_contrato", name="ck_empresa_fechas_contrato"),
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

    def contrato_vigente(self, hoy: date | None = None) -> bool:
        hoy = hoy or date.today()
        return self.fecha_inicio_contrato <= hoy <= self.fecha_termino_contrato
