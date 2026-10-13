"""empty message

Revision ID: b25cc4eed4b0
Revises: c4f2a8e1b7d3
Create Date: 2026-10-13 20:21:40.672527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b25cc4eed4b0'
down_revision: Union[str, None] = 'c4f2a8e1b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
