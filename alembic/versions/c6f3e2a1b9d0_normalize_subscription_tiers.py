"""normalize_subscription_tiers

Revision ID: c6f3e2a1b9d0
Revises: f90d5824709c
Create Date: 2026-04-09 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c6f3e2a1b9d0"
down_revision: Union[str, None] = "f90d5824709c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VALID_TIERS = ("free", "basic", "elite")


def upgrade() -> None:
    valid_tiers = ", ".join(f"'{tier}'" for tier in VALID_TIERS)
    op.execute(
        f"UPDATE users SET subscription_tier = 'elite' "
        f"WHERE subscription_tier NOT IN ({valid_tiers})"
    )


def downgrade() -> None:
    # Legacy nonstandard tiers are intentionally not restored.
    pass

