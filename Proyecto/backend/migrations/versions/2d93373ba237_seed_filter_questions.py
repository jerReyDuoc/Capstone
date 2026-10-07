"""seed filter questions

Revision ID: 2d93373ba237
Revises: 24ce495af093
Create Date: 2026-10-06 22:21:08.972579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d93373ba237'
down_revision: Union[str, None] = '24ce495af093'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PREGUNTAS = [
    ("F1", 1, "¿La organización utiliza, desarrolla o integra algún sistema, modelo o herramienta de IA?", "Determina si la organización tiene exposición a IA. Si la respuesta es NO, no aplica ningún control."),
    ("F2", 2, "¿Procesa datos sensibles (salud, biométricos o perfilamiento de personas/menores)?", "Activa controles reforzados de protección de datos sensibles."),
    ("F3", 3, "¿Utiliza servicios, APIs, SaaS o plataformas de IA proveídos por terceros o en nube internacional?", "Activa controles de transferencia internacional y contratos con encargados."),
    ("F4", 4, "¿Utiliza modelos de lenguaje (LLM), IA Generativa o arquitecturas RAG / bases vectoriales?", "Activa controles específicos de LLM: prompt injection, RAG poisoning, fugas de información."),
    ("F5", 5, "¿La IA genera código/SQL/HTML o ejecuta acciones/agentes conectados a otros sistemas corporativos?", "Activa controles de output handling, exceso de agencia y límites de autonomía."),
    ("F6", 6, "¿La IA toma decisiones o genera resultados que afectan directamente derechos, personas, crédito o contrataciones?", "Activa controles de sesgos, explicabilidad y human-in-the-loop."),
    ("F7", 7, "¿La empresa desarrolla, entrena o adapta internamente sus propios modelos o agentes de IA?", "Activa controles de red teaming y ciclo de vida de desarrollo de IA propia."),
]


def upgrade() -> None:
    conn = op.get_bind()
    for codigo, orden, pregunta, descripcion in PREGUNTAS:
        conn.execute(
            sa.text("""
                INSERT INTO preguntas_filtro (codigo, orden, pregunta, descripcion, activa)
                VALUES (:codigo, :orden, :pregunta, :descripcion, true)
            """),
            {
                "codigo": codigo,
                "orden": orden,
                "pregunta": pregunta,
                "descripcion": descripcion,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM preguntas_filtro"))
