"""HU-10: comparativa sectorial con k-anonimato

  - benchmark.total_empresas   k = organizaciones distintas de la cohorte (base de la supresión
                               k < K_ANONIMATO_MINIMO). total_evaluaciones se conserva.
  - benchmark.percentil_25/75  distribución del rubro (solo se publica con cohortes grandes)
  - fila con dominio_id NULL   puntaje GENERAL del rubro (la crea el recálculo)

Las filas existentes quedan con total_empresas NULL, que cuenta como cohorte insuficiente
(se suprimen) hasta el siguiente recálculo: al completar una evaluación, el cron de las
02:00 UTC o POST /api/admin/benchmark/recalcular.

Revision ID: a7c4e2f9d1b3
Revises: f1d6b3a8c2e4
Create Date: 2026-10-29 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c4e2f9d1b3'
down_revision: Union[str, None] = 'f1d6b3a8c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("benchmark", sa.Column("total_empresas", sa.Integer(), nullable=True))
    op.add_column("benchmark", sa.Column("percentil_25", sa.Float(), nullable=True))
    op.add_column("benchmark", sa.Column("percentil_75", sa.Float(), nullable=True))


def downgrade() -> None:
    # La fila general (dominio_id NULL) no existía antes de HU-10
    op.execute("DELETE FROM benchmark WHERE dominio_id IS NULL")
    op.drop_column("benchmark", "percentil_75")
    op.drop_column("benchmark", "percentil_25")
    op.drop_column("benchmark", "total_empresas")
