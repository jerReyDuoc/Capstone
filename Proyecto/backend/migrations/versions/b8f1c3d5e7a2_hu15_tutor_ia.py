"""HU-15: Agente IA Tutor (conversaciones y mensajes anonimizados)

  - conversacion_tutor            conversación de la empresa con el tutor, atada a la evaluación
                                  vigente al abrirla, con su nivel (Inicial/Intermedio/Avanzado)
  - mensaje_tutor                 mensajes con texto ANONIMIZADO y la respuesta estructurada
                                  del tutor (pasos, brechas, referencias); ON DELETE CASCADE
  - llamadas_llm.conversacion_tutor_id   une cada métrica del LLM con su conversación (sin FK:
                                  la métrica, que no tiene texto, sobrevive al borrado)

Revision ID: b8f1c3d5e7a2
Revises: a4c7e2f9d1b3
Create Date: 2026-10-28 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8f1c3d5e7a2'
down_revision: Union[str, None] = 'a4c7e2f9d1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NIVELES = "('Inicial', 'Intermedio', 'Avanzado')"
_TIPOS = "('pregunta', 'explicacion', 'plan_accion', 'orientacion', 'fuera_de_alcance', 'bloqueado')"


def upgrade() -> None:
    op.create_table(
        'conversacion_tutor',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('empresa_id', sa.Integer(), sa.ForeignKey('empresa.id'), nullable=False),
        sa.Column('usuario_definitivo_id', sa.Integer(), sa.ForeignKey('usuario_definitivo.id'), nullable=False),
        sa.Column('evaluacion_id', sa.Integer(), sa.ForeignKey('evaluacion.id'), nullable=False),
        sa.Column('ruta_formativa_id', sa.Integer(), sa.ForeignKey('ruta_formativa.id'), nullable=True),
        sa.Column('nivel', sa.String(length=12), nullable=False),
        sa.Column('titulo', sa.String(length=120), nullable=True),
        sa.Column('huella_contexto', sa.String(length=32), nullable=True),
        sa.Column('mensajes_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('fecha_ultimo_mensaje', sa.DateTime(), nullable=False),
        sa.CheckConstraint(f"nivel IN {_NIVELES}", name='ck_conversacion_tutor_nivel'),
    )
    op.create_index('ix_conversacion_tutor_empresa_id', 'conversacion_tutor', ['empresa_id'])
    op.create_index('ix_conversacion_tutor_usuario_definitivo_id', 'conversacion_tutor', ['usuario_definitivo_id'])
    op.create_index('ix_conversacion_tutor_fecha_ultimo_mensaje', 'conversacion_tutor', ['fecha_ultimo_mensaje'])

    op.create_table(
        'mensaje_tutor',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversacion_tutor_id', sa.Integer(),
                  sa.ForeignKey('conversacion_tutor.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rol', sa.String(length=10), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('contenido', sa.Text(), nullable=False),
        sa.Column('nivel', sa.String(length=12), nullable=True),
        sa.Column('datos', sa.JSON(), nullable=True),
        sa.Column('bloqueado', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('motivo_bloqueo', sa.String(length=30), nullable=True),
        sa.Column('traza_id', sa.String(length=32), nullable=True),
        sa.Column('prompt_version', sa.String(length=60), nullable=True),
        sa.Column('advertencias', sa.JSON(), nullable=True),
        sa.Column('huella_contexto', sa.String(length=32), nullable=True),
        sa.Column('fecha', sa.DateTime(), nullable=False),
        sa.CheckConstraint("rol IN ('usuario', 'tutor')", name='ck_mensaje_tutor_rol'),
        sa.CheckConstraint(f"tipo IN {_TIPOS}", name='ck_mensaje_tutor_tipo'),
    )
    op.create_index('ix_mensaje_tutor_conversacion_tutor_id', 'mensaje_tutor', ['conversacion_tutor_id'])
    op.create_index('ix_mensaje_tutor_traza_id', 'mensaje_tutor', ['traza_id'])

    with op.batch_alter_table('llamadas_llm') as t:
        t.add_column(sa.Column('conversacion_tutor_id', sa.Integer(), nullable=True))
        t.create_index('ix_llamadas_llm_conversacion_tutor_id', ['conversacion_tutor_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('llamadas_llm') as t:
        t.drop_index('ix_llamadas_llm_conversacion_tutor_id')
        t.drop_column('conversacion_tutor_id')
    op.drop_index('ix_mensaje_tutor_traza_id', table_name='mensaje_tutor')
    op.drop_index('ix_mensaje_tutor_conversacion_tutor_id', table_name='mensaje_tutor')
    op.drop_table('mensaje_tutor')
    op.drop_index('ix_conversacion_tutor_fecha_ultimo_mensaje', table_name='conversacion_tutor')
    op.drop_index('ix_conversacion_tutor_usuario_definitivo_id', table_name='conversacion_tutor')
    op.drop_index('ix_conversacion_tutor_empresa_id', table_name='conversacion_tutor')
    op.drop_table('conversacion_tutor')
