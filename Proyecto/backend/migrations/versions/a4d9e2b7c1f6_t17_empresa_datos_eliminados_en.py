"""T-17: empresa.datos_eliminados_en (retención R7: datos de la empresa tras terminar su gracia)

Marca cuándo la retención borró los documentos, evidencias y conversaciones del tutor de la empresa y
anonimizó su contacto. NULL = aún no. Evita reprocesar a la misma empresa en cada corrida.

Revision ID: a4d9e2b7c1f6
Revises: f1a7c3e9b5d2
Create Date: 2026-11-18 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4d9e2b7c1f6'
down_revision: Union[str, None] = 'f1a7c3e9b5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("empresa", sa.Column("datos_eliminados_en", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("empresa", "datos_eliminados_en")
