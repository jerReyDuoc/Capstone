"""
HU-25 · Configuración de la retención de usuarios temporales (fila única, id = 1).

  fuente_plazo = "entorno"  -> rige RETENCION_DATOS_TITULAR_DIAS (variable de entorno;
                               vacía = regla R1 desactivada). Es el estado inicial.
  fuente_plazo = "panel"    -> rige plazo_titular_dias, que fijó el Oficial de Privacidad
                               en /admin/retencion (NULL = regla R1 desactivada).

ejecucion_desde marca una ejecución EN CURSO (bloqueo simple en la BD): el cron diario y una
ejecución manual no pueden correr a la vez. Se limpia al terminar; si el worker muere, se
considera abandonada pasados RETENCION_BLOQUEO_MAX_MIN minutos.

Quién cambió el plazo y cuándo queda en el audit_log (retencion.configuracion_cambiada),
no aquí: esta tabla no guarda datos personales.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

FUENTE_ENTORNO = "entorno"
FUENTE_PANEL = "panel"
FUENTES = (FUENTE_ENTORNO, FUENTE_PANEL)
ID_UNICO = 1


class ConfiguracionRetencion(Base):
    __tablename__ = "configuracion_retencion"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_configuracion_retencion_fila_unica"),
        CheckConstraint("fuente_plazo IN ('entorno', 'panel')", name="ck_configuracion_retencion_fuente"),
        CheckConstraint("plazo_titular_dias IS NULL OR plazo_titular_dias > 0",
                        name="ck_configuracion_retencion_plazo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=ID_UNICO)
    fuente_plazo: Mapped[str] = mapped_column(String(10), nullable=False, default=FUENTE_ENTORNO)
    plazo_titular_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_actualizacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ejecucion_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
