"""add_is_admin_reply_to_contact_messages

Revision ID: f2a9c1d8e3b5
Revises: b7c4d2e1f9a8
Create Date: 2026-05-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a9c1d8e3b5"
down_revision: Union[str, None] = "b7c4d2e1f9a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("contact_messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_admin_reply",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("contact_messages") as batch_op:
        batch_op.drop_column("is_admin_reply")
