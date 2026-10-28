"""HU-17: puntaje antes y después de cada evidencia de remediación

  - evidencias.puntaje_previo       puntaje general de la evaluación al procesar la evidencia
  - evidencias.puntaje_resultante   puntaje general después del recálculo (igual si no mejoró)

Con ellos la vista de remediación muestra la evolución del puntaje sin recalcular nada.
Va en una migración aparte porque d6e1a4c8f2b5 (HU-26/HU-17) ya pudo haberse aplicado.

Revision ID: e9b4c2d7a1f6
Revises: d6e1a4c8f2b5
Create Date: 2026-10-28 02:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e9b4c2d7a1f6'
down_revision: Union[str, None] = 'd6e1a4c8f2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('evidencias') as t:
        t.add_column(sa.Column('puntaje_previo', sa.Float(), nullable=True))
        t.add_column(sa.Column('puntaje_resultante', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('evidencias') as t:
        t.drop_column('puntaje_resultante')
        t.drop_column('puntaje_previo')
