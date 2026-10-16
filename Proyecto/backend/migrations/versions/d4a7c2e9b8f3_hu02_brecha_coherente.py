"""HU-02: la brecha de una respuesta sigue a su estado vigente

Hasta ahora la brecha se asignaba cuando el estado final pasaba a 'no_cumplido',
pero nunca se quitaba: si la revisión humana o una evidencia nueva dejaban el
control en otro estado, la brecha quedaba colgando. El código ya mantiene la regla
(Respuesta.sincronizar_brecha). Esta migración corrige las filas existentes:
quita la brecha de toda respuesta cuyo estado final no es 'no_cumplido'.

No cambia el esquema. downgrade() no restaura las brechas quitadas (eran incorrectas).

Revision ID: d4a7c2e9b8f3
Revises: b3c8e5d2a7f1
Create Date: 2026-10-16 19:30:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4a7c2e9b8f3'
down_revision: Union[str, None] = 'b3c8e5d2a7f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        'UPDATE respuestas SET "Catalogo_brechas_id_brecha" = NULL '
        'WHERE "Catalogo_brechas_id_brecha" IS NOT NULL '
        "AND estado_clasificacion_final IS DISTINCT FROM 'no_cumplido'"
    )


def downgrade() -> None:
    pass
