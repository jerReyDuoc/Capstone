"""HU-28: sesiones revocables (cerrar sesión) y recuperación de contraseña

Crea:
  - sesion_usuario       una fila por inicio de sesión de un admin o de un usuario
                         definitivo; el token lleva su `sid` y aquí solo queda el SHA-256.
                         Cerrar sesión o restablecer la contraseña marca fecha_cierre y el
                         token deja de servir al instante.
  - token_recuperacion   enlace de recuperación de contraseña de un solo uso (solo SHA-256).

Si tu head no es c9e2f4a7b1d6 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: f3a8d1c6e4b2
Revises: c9e2f4a7b1d6
Create Date: 2026-10-27 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8d1c6e4b2'
down_revision: Union[str, None] = 'c9e2f4a7b1d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK_ROL = "actor_rol IN ('admin_therion', 'cliente')"


def upgrade() -> None:
    op.create_table(
        'sesion_usuario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sid_hash', sa.String(length=64), nullable=False),
        sa.Column('actor_rol', sa.String(length=20), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=False),
        sa.Column('fecha_inicio', sa.DateTime(), nullable=False),
        sa.Column('fecha_expiracion', sa.DateTime(), nullable=False),
        sa.Column('fecha_cierre', sa.DateTime(), nullable=True),
        sa.Column('motivo_cierre', sa.String(length=20), nullable=True),
        sa.CheckConstraint(_CHECK_ROL, name='ck_sesion_usuario_rol'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sid_hash'),
    )
    op.create_index('ix_sesion_usuario_actor', 'sesion_usuario', ['actor_rol', 'actor_id'])

    op.create_table(
        'token_recuperacion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('actor_rol', sa.String(length=20), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('fecha_expiracion', sa.DateTime(), nullable=False),
        sa.Column('fecha_uso', sa.DateTime(), nullable=True),
        sa.Column('fecha_revocacion', sa.DateTime(), nullable=True),
        sa.CheckConstraint(_CHECK_ROL, name='ck_token_recuperacion_rol'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_token_recuperacion_actor', 'token_recuperacion', ['actor_rol', 'actor_id'])


def downgrade() -> None:
    op.drop_index('ix_token_recuperacion_actor', table_name='token_recuperacion')
    op.drop_table('token_recuperacion')
    op.drop_index('ix_sesion_usuario_actor', table_name='sesion_usuario')
    op.drop_table('sesion_usuario')
