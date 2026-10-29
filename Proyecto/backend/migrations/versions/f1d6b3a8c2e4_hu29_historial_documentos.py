"""HU-29: historial de evaluaciones, reevaluación desde la cuenta y "Mis documentos"

  - evaluacion.origen admite 'empresa'          reevaluación iniciada por el usuario definitivo:
                                                pertenece a la empresa desde que nace, sin
                                                usuario temporal
  - evaluacion.fecha_completado                 cuándo se completó (las anteriores quedan NULL y
                                                el historial usa fecha_inicio)
  - uq_evaluacion_empresa_en_curso (PostgreSQL) una sola reevaluación abierta por empresa
  - documento_empresa                           informes PDF archivados y borradores (HU-16)
  - evidencias.fecha_eliminacion                el usuario borró el archivo desde "Mis documentos"
  - avance_formativo.fecha_eliminacion_constancia   el usuario borró la constancia

Nada cambia para los datos existentes: ninguna evaluación tiene origen 'empresa' todavía.

Revision ID: f1d6b3a8c2e4
Revises: c3d9a1f7e5b8
Create Date: 2026-10-29 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1d6b3a8c2e4'
down_revision: Union[str, None] = 'c3d9a1f7e5b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORIGEN_HU19 = "origen IN ('invitacion', 'publica')"
_ORIGEN_HU29 = "origen IN ('invitacion', 'publica', 'empresa')"
_EN_CURSO = "origen = 'empresa' AND estado_progreso NOT IN ('completada', 'cerrada')"


def _es_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    with op.batch_alter_table('evaluacion') as t:
        t.add_column(sa.Column('fecha_completado', sa.DateTime(), nullable=True))
        t.drop_constraint('ck_evaluacion_origen', type_='check')
        t.create_check_constraint('ck_evaluacion_origen', _ORIGEN_HU29)
    if _es_postgres():
        # Defensa en la BD además del bloqueo de la fila de la empresa en el caso de uso
        op.create_index('uq_evaluacion_empresa_en_curso', 'evaluacion', ['empresa_id'], unique=True,
                        postgresql_where=sa.text(_EN_CURSO))

    op.create_table(
        'documento_empresa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('evaluacion_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('storage_path', sa.String(length=512), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('tamano_bytes', sa.Integer(), nullable=False),
        sa.Column('hash_contenido', sa.String(length=64), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('creado_por_usuario_id', sa.Integer(), nullable=True),
        sa.CheckConstraint("tipo IN ('informe_pdf', 'borrador')", name='ck_documento_empresa_tipo'),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresa.id']),
        sa.ForeignKeyConstraint(['evaluacion_id'], ['evaluacion.id']),
        sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['usuario_definitivo.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documento_empresa_empresa_id', 'documento_empresa', ['empresa_id'], unique=False)
    op.create_index('ix_documento_empresa_evaluacion_id', 'documento_empresa', ['evaluacion_id'], unique=False)

    with op.batch_alter_table('evidencias') as t:
        t.add_column(sa.Column('fecha_eliminacion', sa.DateTime(), nullable=True))
    with op.batch_alter_table('avance_formativo') as t:
        t.add_column(sa.Column('fecha_eliminacion_constancia', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('avance_formativo') as t:
        t.drop_column('fecha_eliminacion_constancia')
    with op.batch_alter_table('evidencias') as t:
        t.drop_column('fecha_eliminacion')

    # Los archivos de STORAGE_DIR no se tocan: bórralos a mano si haces downgrade en producción.
    op.drop_index('ix_documento_empresa_evaluacion_id', table_name='documento_empresa')
    op.drop_index('ix_documento_empresa_empresa_id', table_name='documento_empresa')
    op.drop_table('documento_empresa')

    if _es_postgres():
        op.drop_index('uq_evaluacion_empresa_en_curso', table_name='evaluacion')
    # Las reevaluaciones de empresa no caben en el esquema anterior: pasan a 'invitacion'
    op.execute("UPDATE evaluacion SET origen = 'invitacion' WHERE origen = 'empresa'")
    with op.batch_alter_table('evaluacion') as t:
        t.drop_constraint('ck_evaluacion_origen', type_='check')
        t.create_check_constraint('ck_evaluacion_origen', _ORIGEN_HU19)
        t.drop_column('fecha_completado')
