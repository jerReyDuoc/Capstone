"""HU-16: borradores de documentos de cumplimiento (Política de uso de LLM, Aviso de privacidad, PIA)

  - borrador_documento   borrador en revisión de la empresa: contenido Markdown CIFRADO
                         (TextoCifradoBorrador, prefijo enc:v1:), versión para el control de
                         edición concurrente y, al consolidarse, el PDF guardado en
                         "Mis documentos" (documento_empresa, tipo 'borrador', HU-29).

documento_empresa ya admite el tipo 'borrador' desde HU-29: no cambia.
El rol complianceia_app (HU-09) recibe los permisos por ALTER DEFAULT PRIVILEGES.

Si tu head no es e5a9c3f1b7d2 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: b6d2f9a4c8e1
Revises: e5a9c3f1b7d2
Create Date: 2026-11-03 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b6d2f9a4c8e1'
down_revision: Union[str, None] = 'e5a9c3f1b7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'borrador_documento',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('evaluacion_id', sa.Integer(), nullable=True),
        sa.Column('usuario_definitivo_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('titulo', sa.String(length=150), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('contenido', sa.Text(), nullable=False),
        sa.Column('adaptado_ia', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('prompt_version', sa.String(length=40), nullable=True),
        sa.Column('traza_id', sa.String(length=32), nullable=True),
        sa.Column('version_plantillas', sa.String(length=20), nullable=False),
        sa.Column('huella_contexto', sa.String(length=32), nullable=True),
        sa.Column('notas', sa.JSON(), nullable=True),
        sa.Column('advertencias', sa.JSON(), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), nullable=False),
        sa.Column('fecha_actualizacion', sa.DateTime(), nullable=False),
        sa.Column('fecha_consolidacion', sa.DateTime(), nullable=True),
        sa.Column('documento_id', sa.Integer(), nullable=True),
        sa.CheckConstraint("tipo IN ('politica_llm', 'aviso_privacidad', 'pia')", name='ck_borrador_documento_tipo'),
        sa.CheckConstraint("estado IN ('en_revision', 'consolidado')", name='ck_borrador_documento_estado'),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresa.id']),
        sa.ForeignKeyConstraint(['evaluacion_id'], ['evaluacion.id']),
        sa.ForeignKeyConstraint(['usuario_definitivo_id'], ['usuario_definitivo.id']),
        # Si el usuario borra el PDF consolidado en "Mis documentos", el borrador queda sin él
        sa.ForeignKeyConstraint(['documento_id'], ['documento_empresa.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_borrador_documento_empresa_id', 'borrador_documento', ['empresa_id'], unique=False)


def downgrade() -> None:
    # Los PDF consolidados siguen en documento_empresa ("Mis documentos"): no se tocan.
    op.drop_index('ix_borrador_documento_empresa_id', table_name='borrador_documento')
    op.drop_table('borrador_documento')
