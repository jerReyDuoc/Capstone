"""HU-22: bandeja de revisión del Oficial de Cumplimiento

  respuestas         + comentario_revision   (texto del oficial, anonimizado antes de guardar)
                     + decision_revision     confirmada | corregida
                     + revisor_admin_id      quién fijó la clasificación final (usuarios_admin)
  eventos_seguridad  + resolucion            ataque_confirmado | falso_positivo
                     + comentario_revision   (anonimizado)
                     + fecha_revision        UTC
                     + revisor_admin_id

Solo agrega columnas NULL: no toca datos existentes. Las revisiones anteriores a HU-22
quedan sin decisión ni comentario (la bandeja las muestra como "revisada, sin comentario").
El rol complianceia_app (HU-09) ya tiene UPDATE sobre ambas tablas.

Si tu head no es f8c2a6d4e1b7 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: c7d3e9a1f5b8
Revises: f8c2a6d4e1b7
Create Date: 2026-11-04 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d3e9a1f5b8'
down_revision: Union[str, None] = 'f8c2a6d4e1b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("respuestas", sa.Column("comentario_revision", sa.Text(), nullable=True))
    op.add_column("respuestas", sa.Column("decision_revision", sa.String(length=10), nullable=True))
    op.add_column("respuestas", sa.Column(
        "revisor_admin_id", sa.Integer(), sa.ForeignKey("usuarios_admin.id_admin"), nullable=True))
    # La bandeja filtra por "pendiente" (sin revisión) dentro de lo que el LLM o la seguridad tocó
    op.create_index("ix_respuestas_fuente_revision", "respuestas",
                    ["fuente_clasificacion", "clasificacion_revisada"])

    op.add_column("eventos_seguridad", sa.Column("resolucion", sa.String(length=20), nullable=True))
    op.add_column("eventos_seguridad", sa.Column("comentario_revision", sa.Text(), nullable=True))
    op.add_column("eventos_seguridad", sa.Column("fecha_revision", sa.DateTime(), nullable=True))
    op.add_column("eventos_seguridad", sa.Column(
        "revisor_admin_id", sa.Integer(), sa.ForeignKey("usuarios_admin.id_admin"), nullable=True))
    op.create_index("ix_eventos_seguridad_revisado", "eventos_seguridad", ["revisado", "fecha"])


def downgrade() -> None:
    op.drop_index("ix_eventos_seguridad_revisado", table_name="eventos_seguridad")
    op.drop_column("eventos_seguridad", "revisor_admin_id")
    op.drop_column("eventos_seguridad", "fecha_revision")
    op.drop_column("eventos_seguridad", "comentario_revision")
    op.drop_column("eventos_seguridad", "resolucion")
    op.drop_index("ix_respuestas_fuente_revision", table_name="respuestas")
    op.drop_column("respuestas", "revisor_admin_id")
    op.drop_column("respuestas", "decision_revision")
    op.drop_column("respuestas", "comentario_revision")
