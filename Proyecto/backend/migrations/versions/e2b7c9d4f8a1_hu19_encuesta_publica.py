"""HU-19: encuesta pública desde la landing (y aceptación del aviso legal, HU-04)

  1. evaluacion.origen ('invitacion' | 'publica'). Las existentes quedan como 'invitacion'.
     evaluacion.es_prueba (false): las marcadas por un admin no entran al benchmark.
  2. usuario_temporal.aviso_legal_version y fecha_aceptacion_aviso: qué versión del
     aviso legal aceptó el encuestado y cuándo (UTC).
  3. Índice por origen (el listado de evaluaciones y el benchmark filtran por él).

Revision ID: e2b7c9d4f8a1
Revises: d4a7c2e9b8f3
Create Date: 2026-10-21 14:00:00

IMPORTANTE: si en tu repo local hay migraciones posteriores a d4a7c2e9b8f3 que aún no
están en main, cambia down_revision por tu head actual (`alembic heads`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2b7c9d4f8a1'
down_revision: Union[str, None] = 'd4a7c2e9b8f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'evaluacion',
        sa.Column('origen', sa.String(length=20), nullable=False, server_default='invitacion'),
    )
    op.create_check_constraint(
        'ck_evaluacion_origen', 'evaluacion', "origen IN ('invitacion', 'publica')"
    )
    op.create_index('ix_evaluacion_origen', 'evaluacion', ['origen'])
    op.add_column(
        'evaluacion',
        sa.Column('es_prueba', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column('usuario_temporal', sa.Column('aviso_legal_version', sa.String(length=20), nullable=True))
    op.add_column('usuario_temporal', sa.Column('fecha_aceptacion_aviso', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('usuario_temporal', 'fecha_aceptacion_aviso')
    op.drop_column('usuario_temporal', 'aviso_legal_version')
    op.drop_column('evaluacion', 'es_prueba')
    op.drop_index('ix_evaluacion_origen', table_name='evaluacion')
    op.drop_constraint('ck_evaluacion_origen', 'evaluacion', type_='check')
    op.drop_column('evaluacion', 'origen')
