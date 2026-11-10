"""HU-33: regla del detector en los eventos de seguridad

  eventos_seguridad  + regla   identificador de la regla que bloqueó el texto
                               ("manipulacion.aprueba", "oculto.bidi",
                               "codificado.base64>inyeccion.ignorar_instrucciones"...).
                               Nunca contiene texto del usuario.

Sirve para que el Oficial de Cumplimiento revise desde su bandeja (HU-22) si un bloqueo
fue un falso positivo y qué regla conviene afinar. Solo agrega una columna NULL: los
eventos anteriores a HU-33 quedan sin regla. El rol complianceia_app (HU-09) ya tiene
INSERT sobre la tabla.

Si tu head no es c7d3e9a1f5b8 (`alembic heads`), cambia down_revision por el tuyo.

Revision ID: d4b8e2f6a9c3
Revises: c7d3e9a1f5b8
Create Date: 2026-11-10 16:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4b8e2f6a9c3'
down_revision: Union[str, None] = 'c7d3e9a1f5b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("eventos_seguridad", sa.Column("regla", sa.String(length=80), nullable=True))
    # La bandeja agrupa los falsos positivos por regla para afinar el detector
    op.create_index("ix_eventos_seguridad_regla", "eventos_seguridad", ["regla"])


def downgrade() -> None:
    op.drop_index("ix_eventos_seguridad_regla", table_name="eventos_seguridad")
    op.drop_column("eventos_seguridad", "regla")
