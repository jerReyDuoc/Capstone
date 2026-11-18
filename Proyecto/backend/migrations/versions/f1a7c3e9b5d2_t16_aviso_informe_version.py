"""T-16: evaluacion.aviso_informe_version (versión del aviso legal con que se emitió el informe)

La primera emisión del informe fija la versión vigente del aviso y queda congelada: un informe
emitido con 2026-11-v1 se sigue mostrando con v1 aunque el aviso vigente sea v2. Las evaluaciones
ya completadas pudieron emitir informe antes de esta migración, siempre con 2026-11-v1.

Si tu head no es b3e9d5a1c7f4 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: f1a7c3e9b5d2
Revises: b3e9d5a1c7f4
Create Date: 2026-11-18 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a7c3e9b5d2'
down_revision: Union[str, None] = 'b3e9d5a1c7f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evaluacion", sa.Column("aviso_informe_version", sa.String(length=20), nullable=True))
    op.execute("UPDATE evaluacion SET aviso_informe_version = '2026-11-v1' WHERE fecha_completado IS NOT NULL")


def downgrade() -> None:
    op.drop_column("evaluacion", "aviso_informe_version")
