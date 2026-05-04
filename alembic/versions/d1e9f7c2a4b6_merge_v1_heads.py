"""merge_v1_heads

Revision ID: d1e9f7c2a4b6
Revises: 3a1b2c4d5e6f, c6f3e2a1b9d0
Create Date: 2026-04-09 19:25:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "d1e9f7c2a4b6"
down_revision: Union[str, tuple[str, str], None] = ("3a1b2c4d5e6f", "c6f3e2a1b9d0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

