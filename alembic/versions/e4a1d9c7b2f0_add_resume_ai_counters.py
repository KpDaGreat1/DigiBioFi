"""add_resume_ai_counters

Revision ID: e4a1d9c7b2f0
Revises: d1e9f7c2a4b6
Create Date: 2026-05-01 18:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e4a1d9c7b2f0"
down_revision: Union[str, None] = "d1e9f7c2a4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("resume_ai_requests_today", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("resume_ai_last_request_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "resume_ai_last_request_at")
    op.drop_column("users", "resume_ai_requests_today")
