"""add_private_contact_fields_to_users

Revision ID: a9f4b1c2d3e4
Revises: e4a1d9c7b2f0
Create Date: 2026-05-01 16:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9f4b1c2d3e4"
down_revision: Union[str, None] = "e4a1d9c7b2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=50), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("address", sa.String(length=200), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("users", "address")
    op.drop_column("users", "phone")
