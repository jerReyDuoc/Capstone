"""solicitudes de derechos ARCOP y su historial de eventos

Revision ID: e5a1c9d4b2f7
Revises: a168283ff2b8
Create Date: 2026-10-13 22:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a1c9d4b2f7'
down_revision: Union[str, None] = 'a168283ff2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIPOS = "('acceso','rectificacion','supresion','oposicion','portabilidad','bloqueo')"
ESTADOS = ("('recibida','en_revision','pendiente_informacion','en_proceso',"
           "'resuelta','rechazada','cancelada')")


def upgrade() -> None:
    op.create_table('solicitudes_arcop',
    sa.Column('id_solicitud', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('estado', sa.String(length=25), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('Usuario_temporal_id', sa.Integer(), nullable=False),
    sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
    sa.Column('fecha_actualizacion', sa.DateTime(), nullable=False),
    sa.Column('fecha_cierre', sa.DateTime(), nullable=True),
    sa.Column('respuesta', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['Usuario_temporal_id'], ['usuario_temporal.id'], ),
    sa.CheckConstraint(f"tipo IN {TIPOS}", name='ck_solicitudes_arcop_tipo'),
    sa.CheckConstraint(f"estado IN {ESTADOS}", name='ck_solicitudes_arcop_estado'),
    sa.PrimaryKeyConstraint('id_solicitud')
    )
    op.create_index('ix_solicitudes_arcop_Usuario_temporal_id', 'solicitudes_arcop', ['Usuario_temporal_id'], unique=False)
    op.create_index('ix_solicitudes_arcop_estado', 'solicitudes_arcop', ['estado'], unique=False)

    op.create_table('eventos_solicitud_arcop',
    sa.Column('id_evento', sa.Integer(), nullable=False),
    sa.Column('Solicitudes_arcop_id_solicitud', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.DateTime(), nullable=False),
    sa.Column('tipo_evento', sa.String(length=25), nullable=False),
    sa.Column('estado_anterior', sa.String(length=25), nullable=True),
    sa.Column('estado_nuevo', sa.String(length=25), nullable=False),
    sa.Column('actor_rol', sa.String(length=20), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('comentario', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['Solicitudes_arcop_id_solicitud'], ['solicitudes_arcop.id_solicitud'], ),
    sa.PrimaryKeyConstraint('id_evento')
    )
    op.create_index('ix_eventos_solicitud_arcop_Solicitudes_arcop_id_solicitud', 'eventos_solicitud_arcop', ['Solicitudes_arcop_id_solicitud'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_eventos_solicitud_arcop_Solicitudes_arcop_id_solicitud', table_name='eventos_solicitud_arcop')
    op.drop_table('eventos_solicitud_arcop')
    op.drop_index('ix_solicitudes_arcop_estado', table_name='solicitudes_arcop')
    op.drop_index('ix_solicitudes_arcop_Usuario_temporal_id', table_name='solicitudes_arcop')
    op.drop_table('solicitudes_arcop')
