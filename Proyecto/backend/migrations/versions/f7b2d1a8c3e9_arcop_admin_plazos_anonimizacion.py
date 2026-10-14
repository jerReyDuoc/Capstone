"""ARCOP: administradores, plazos de solicitudes y marca de anonimización

Revision ID: f7b2d1a8c3e9
Revises: e5a1c9d4b2f7
Create Date: 2026-10-14 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b2d1a8c3e9'
down_revision: Union[str, None] = 'e5a1c9d4b2f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('usuarios_admin',
    sa.Column('id_admin', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.String(length=200), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
    sa.Column('ultimo_acceso', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id_admin'),
    sa.UniqueConstraint('email')
    )

    op.add_column('solicitudes_arcop', sa.Column('fecha_limite_respuesta', sa.DateTime(), nullable=True))
    op.add_column('solicitudes_arcop', sa.Column('fecha_limite_informacion', sa.DateTime(), nullable=True))

    op.add_column('usuario_temporal', sa.Column('fecha_anonimizacion', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('usuario_temporal', 'fecha_anonimizacion')
    op.drop_column('solicitudes_arcop', 'fecha_limite_informacion')
    op.drop_column('solicitudes_arcop', 'fecha_limite_respuesta')
    op.drop_table('usuarios_admin')
