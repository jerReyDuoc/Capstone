"""add eventos_seguridad (registro de prompt injection)

Revision ID: 7c1e5a9d3f20
Revises: 2d93373ba237
Create Date: 2026-10-06 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c1e5a9d3f20'
down_revision: Union[str, None] = '2d93373ba237'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('eventos_seguridad',
    sa.Column('id_evento', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.DateTime(), nullable=False),
    sa.Column('tipo', sa.String(length=30), nullable=False),
    sa.Column('origen', sa.String(length=20), nullable=False),
    sa.Column('Evaluacion_id', sa.Integer(), nullable=True),
    sa.Column('Matriz_controles_id_control', sa.Integer(), nullable=True),
    sa.Column('Respuestas_id_respuesta', sa.Integer(), nullable=True),
    sa.Column('Evidencias_id_evidencia', sa.Integer(), nullable=True),
    sa.Column('extracto', sa.Text(), nullable=True),
    sa.Column('hash_texto', sa.String(length=64), nullable=False),
    sa.Column('revisado', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.ForeignKeyConstraint(['Evaluacion_id'], ['evaluacion.id'], ),
    sa.ForeignKeyConstraint(['Matriz_controles_id_control'], ['matriz_controles.id_control'], ),
    sa.ForeignKeyConstraint(['Respuestas_id_respuesta'], ['respuestas.id_respuesta'], ),
    sa.ForeignKeyConstraint(['Evidencias_id_evidencia'], ['evidencias.id_evidencia'], ),
    sa.PrimaryKeyConstraint('id_evento')
    )
    op.create_index('ix_eventos_seguridad_hash_texto', 'eventos_seguridad', ['hash_texto'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_eventos_seguridad_hash_texto', table_name='eventos_seguridad')
    op.drop_table('eventos_seguridad')
