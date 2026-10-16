"""HU-01: una respuesta por (evaluación, control)

Antes POST /api/respuestas siempre insertaba: responder dos veces un control
duplicaba la fila y distorsionaba el puntaje. Esta migración:

  1. Fusiona los duplicados existentes: por cada (evaluación, control) conserva la
     respuesta MÁS RECIENTE (mayor id_respuesta) y le traspasa las filas hijas de
     las demás (evidencias, eventos de seguridad, llamadas al LLM y
     sanitizaciones), para no perder trazabilidad. Luego borra las duplicadas.
  2. Crea la restricción única uq_respuesta_evaluacion_control, que además deja un
     índice por "Evaluacion_id" (lo usan el listado y el endpoint de progreso).

downgrade() solo quita la restricción: las filas fusionadas no se recuperan.

Revision ID: 9a4e2c7b1f05
Revises: f7b2d1a8c3e9
Create Date: 2026-10-15 23:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '9a4e2c7b1f05'
down_revision: Union[str, None] = 'f7b2d1a8c3e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tablas que referencian respuestas.id_respuesta
_HIJAS = ("evidencias", "eventos_seguridad", "llamadas_llm", "sanitizaciones")

# Mapa duplicada -> conservada (la de mayor id del mismo par evaluación+control)
_MAPA = """
    SELECT id_respuesta AS duplicada, conservada FROM (
        SELECT id_respuesta,
               MAX(id_respuesta) OVER (
                   PARTITION BY "Evaluacion_id", "Matriz_controles_id_control"
               ) AS conservada
        FROM respuestas
        WHERE "Evaluacion_id" IS NOT NULL
          AND "Matriz_controles_id_control" IS NOT NULL
    ) t
    WHERE id_respuesta <> conservada
"""


def upgrade() -> None:
    op.execute(f"CREATE TEMPORARY TABLE _hu01_duplicadas AS {_MAPA}")
    for tabla in _HIJAS:
        op.execute(
            f'UPDATE {tabla} h SET "Respuestas_id_respuesta" = d.conservada '
            f'FROM _hu01_duplicadas d WHERE h."Respuestas_id_respuesta" = d.duplicada'
        )
    op.execute(
        "DELETE FROM respuestas WHERE id_respuesta IN (SELECT duplicada FROM _hu01_duplicadas)"
    )
    op.execute("DROP TABLE _hu01_duplicadas")

    op.create_unique_constraint(
        "uq_respuesta_evaluacion_control",
        "respuestas",
        ["Evaluacion_id", "Matriz_controles_id_control"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_respuesta_evaluacion_control", "respuestas", type_="unique")
