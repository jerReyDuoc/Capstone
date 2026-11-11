"""HU-25: plazo de retención de usuarios temporales configurable

  configuracion_retencion   fila única (id = 1)
    fuente_plazo            'entorno' (rige RETENCION_DATOS_TITULAR_DIAS) | 'panel'
    plazo_titular_dias      días después de vencer el acceso del usuario temporal (si 'panel')
    fecha_actualizacion     último cambio desde el panel
    ejecucion_desde         marca de una ejecución en curso (evita dos a la vez)

Se siembra la fila con fuente 'entorno': al migrar no cambia nada respecto de T-06 hasta que
el Oficial de Privacidad fije un plazo en /admin/retencion. Sin datos personales (quién cambió
el plazo queda en el audit_log). El rol complianceia_app (HU-09) recibe los permisos por los
DEFAULT PRIVILEGES que dejó esa migración.

Si tu head no es d4b8e2f6a9c3 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: e7c3a9f2b6d4
Revises: d4b8e2f6a9c3
Create Date: 2026-11-10 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7c3a9f2b6d4'
down_revision: Union[str, None] = 'd4b8e2f6a9c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tabla = op.create_table(
        "configuracion_retencion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fuente_plazo", sa.String(length=10), nullable=False, server_default="entorno"),
        sa.Column("plazo_titular_dias", sa.Integer(), nullable=True),
        sa.Column("fecha_actualizacion", sa.DateTime(), nullable=True),
        sa.Column("ejecucion_desde", sa.DateTime(), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_configuracion_retencion_fila_unica"),
        sa.CheckConstraint("fuente_plazo IN ('entorno', 'panel')", name="ck_configuracion_retencion_fuente"),
        sa.CheckConstraint("plazo_titular_dias IS NULL OR plazo_titular_dias > 0",
                           name="ck_configuracion_retencion_plazo"),
    )
    op.bulk_insert(tabla, [{"id": 1, "fuente_plazo": "entorno", "plazo_titular_dias": None}])


def downgrade() -> None:
    op.drop_table("configuracion_retencion")
