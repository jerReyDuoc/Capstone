"""HU-31: solicitud de contratación desde los resultados

Amplía la tabla solicitud_contratacion (base mínima creada en HU-27):
  - cargo_contacto                        cargo de quien pide contratar (criterio 1)
  - consentimiento_contacto_version       consentimiento de CONTACTO COMERCIAL, separado del
  - fecha_consentimiento_contacto         de traspaso (criterio 2), con su versión y fecha
  - estados de la bandeja (criterio 3): 'pendiente' pasa a 'nueva' y se agrega 'contactada'
    (se mantienen 'contratada', 'descartada' y el técnico 'migrada' de HU-27).

Las filas anteriores conservan sus datos; las que estaban en 'pendiente' quedan en 'nueva'
y con el consentimiento de contacto en NULL (se pidieron antes de que existiera).

Si tu head no es b7e4d2a9c6f1 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: c9e2f4a7b1d6
Revises: b7e4d2a9c6f1
Create Date: 2026-10-27 03:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e2f4a7b1d6'
down_revision: Union[str, None] = 'b7e4d2a9c6f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK = "ck_solicitud_contratacion_estado"
_ESTADOS_NUEVOS = "estado IN ('nueva', 'contactada', 'contratada', 'migrada', 'descartada')"
_ESTADOS_HU27 = "estado IN ('pendiente', 'contratada', 'migrada', 'descartada')"


def upgrade() -> None:
    # 1. Se quita el CHECK antes de renombrar el estado (si no, 'nueva' lo violaría)
    with op.batch_alter_table('solicitud_contratacion') as batch:
        batch.drop_constraint(_CHECK, type_='check')
        batch.add_column(sa.Column('cargo_contacto', sa.String(length=80), nullable=True))
        batch.add_column(sa.Column('consentimiento_contacto_version', sa.String(length=20), nullable=True))
        batch.add_column(sa.Column('fecha_consentimiento_contacto', sa.DateTime(), nullable=True))

    op.execute("UPDATE solicitud_contratacion SET estado = 'nueva' WHERE estado = 'pendiente'")

    with op.batch_alter_table('solicitud_contratacion') as batch:
        batch.alter_column('estado', existing_type=sa.String(length=20), existing_nullable=False,
                           server_default='nueva')
        batch.create_check_constraint(_CHECK, _ESTADOS_NUEVOS)
    # Bandeja del admin: se filtra por estado y se ordena por id
    op.create_index('ix_solicitud_contratacion_estado', 'solicitud_contratacion', ['estado'])


def downgrade() -> None:
    op.drop_index('ix_solicitud_contratacion_estado', table_name='solicitud_contratacion')
    with op.batch_alter_table('solicitud_contratacion') as batch:
        batch.drop_constraint(_CHECK, type_='check')

    # 'contactada' no existía en HU-27: vuelve a 'pendiente' (sigue sin contratar)
    op.execute("UPDATE solicitud_contratacion SET estado = 'pendiente' WHERE estado IN ('nueva', 'contactada')")

    with op.batch_alter_table('solicitud_contratacion') as batch:
        batch.alter_column('estado', existing_type=sa.String(length=20), existing_nullable=False,
                           server_default='pendiente')
        batch.create_check_constraint(_CHECK, _ESTADOS_HU27)
        batch.drop_column('fecha_consentimiento_contacto')
        batch.drop_column('consentimiento_contacto_version')
        batch.drop_column('cargo_contacto')
