"""capa de politicas e IA: llamadas_llm, sanitizaciones y revision humana

Revision ID: c4f2a8e1b7d3
Revises: a53fb924d0ac
Create Date: 2026-10-12 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f2a8e1b7d3'
down_revision: Union[str, None] = 'a53fb924d0ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fks():
    return [
        sa.Column('Evaluacion_id', sa.Integer(), nullable=True),
        sa.Column('Respuestas_id_respuesta', sa.Integer(), nullable=True),
        sa.Column('Evidencias_id_evidencia', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['Evaluacion_id'], ['evaluacion.id'], ),
        sa.ForeignKeyConstraint(['Respuestas_id_respuesta'], ['respuestas.id_respuesta'], ),
        sa.ForeignKeyConstraint(['Evidencias_id_evidencia'], ['evidencias.id_evidencia'], ),
    ]


def upgrade() -> None:
    op.create_table('llamadas_llm',
    sa.Column('id_llamada', sa.Integer(), nullable=False),
    sa.Column('traza_id', sa.String(length=32), nullable=False),
    sa.Column('fecha', sa.DateTime(), nullable=False),
    sa.Column('tarea', sa.String(length=40), nullable=False),
    sa.Column('proveedor', sa.String(length=30), nullable=False),
    sa.Column('modelo', sa.String(length=100), nullable=False),
    sa.Column('prompt_version', sa.String(length=60), nullable=False),
    sa.Column('exito', sa.Boolean(), nullable=False),
    sa.Column('tipo_error', sa.String(length=30), nullable=True),
    sa.Column('detalle_error', sa.Text(), nullable=True),
    sa.Column('tokens_entrada', sa.Integer(), nullable=True),
    sa.Column('tokens_salida', sa.Integer(), nullable=True),
    sa.Column('costo_estimado_usd', sa.Float(), nullable=True),
    sa.Column('latencia_ms', sa.Float(), nullable=True),
    sa.Column('sanitizado', sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column('entidades_anonimizadas', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('clasificacion', sa.String(length=25), nullable=True),
    sa.Column('confianza', sa.Float(), nullable=True),
    sa.Column('advertencias', sa.JSON(), nullable=True),
    *_fks(),
    sa.PrimaryKeyConstraint('id_llamada')
    )
    op.create_index('ix_llamadas_llm_traza_id', 'llamadas_llm', ['traza_id'], unique=False)
    op.create_index('ix_llamadas_llm_fecha', 'llamadas_llm', ['fecha'], unique=False)
    op.create_index('ix_llamadas_llm_Respuestas_id_respuesta', 'llamadas_llm', ['Respuestas_id_respuesta'], unique=False)

    op.create_table('sanitizaciones',
    sa.Column('id_sanitizacion', sa.Integer(), nullable=False),
    sa.Column('traza_id', sa.String(length=32), nullable=False),
    sa.Column('fecha', sa.DateTime(), nullable=False),
    sa.Column('campo', sa.String(length=30), nullable=False),
    sa.Column('motor', sa.String(length=120), nullable=False),
    sa.Column('duracion_ms', sa.Float(), nullable=False),
    sa.Column('truncado', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column('total_entidades', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('conteo_por_tipo', sa.JSON(), nullable=True),
    sa.Column('entidades', sa.JSON(), nullable=True),
    sa.Column('mapa_cifrado', sa.Text(), nullable=True),
    *_fks(),
    sa.PrimaryKeyConstraint('id_sanitizacion')
    )
    op.create_index('ix_sanitizaciones_traza_id', 'sanitizaciones', ['traza_id'], unique=False)
    op.create_index('ix_sanitizaciones_Evidencias_id_evidencia', 'sanitizaciones', ['Evidencias_id_evidencia'], unique=False)

    op.add_column('respuestas', sa.Column('clasificacion_revisada', sa.String(length=25), nullable=True))
    op.add_column('respuestas', sa.Column('fecha_revision', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('respuestas', 'fecha_revision')
    op.drop_column('respuestas', 'clasificacion_revisada')
    op.drop_index('ix_sanitizaciones_Evidencias_id_evidencia', table_name='sanitizaciones')
    op.drop_index('ix_sanitizaciones_traza_id', table_name='sanitizaciones')
    op.drop_table('sanitizaciones')
    op.drop_index('ix_llamadas_llm_Respuestas_id_respuesta', table_name='llamadas_llm')
    op.drop_index('ix_llamadas_llm_fecha', table_name='llamadas_llm')
    op.drop_index('ix_llamadas_llm_traza_id', table_name='llamadas_llm')
    op.drop_table('llamadas_llm')
