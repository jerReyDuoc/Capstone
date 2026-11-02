"""HU-21: versión de la matriz de controles con la que se completó cada evaluación

  - evaluacion.version_matriz VARCHAR(40) NULL ("<MATRIZ_VERSION>+<huella SHA-256>")

La fija POST /completar. Las evaluaciones completadas antes de esta migración quedan en
NULL: su informe imprime la versión vigente al emitirlo, con una nota que lo aclara (no se
inventa una versión que no se registró).

El rol limitado de la API (HU-09, complianceia_app) ya tiene UPDATE sobre toda la tabla
evaluacion, así que no hace falta otro GRANT para la columna nueva.

Revision ID: e5a9c3f1b7d2
Revises: d2f8a6c4e1b9
Create Date: 2026-11-02 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5a9c3f1b7d2'
down_revision: Union[str, None] = 'd2f8a6c4e1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evaluacion", sa.Column("version_matriz", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluacion", "version_matriz")
