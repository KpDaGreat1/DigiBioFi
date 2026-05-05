"""Add Stripe Identity fields and notifications table

Revision ID: g1a2b3c4d5e6
Revises: f2a9c1d8e3b5, a9f4b1c2d3e4
Create Date: 2026-05-05 00:00:00.000000
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, tuple[str, str], None] = "f2a9c1d8e3b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stripe Identity fields on users
    op.add_column(
        "users",
        sa.Column("stripe_verification_id", sa.String(200), nullable=False, server_default=""),
    )
    op.add_column(
        "users",
        sa.Column("verification_status", sa.String(30), nullable=False, server_default=""),
    )

    # Notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False, server_default="system"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("link", sa.String(500), nullable=False, server_default=""),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_column("users", "verification_status")
    op.drop_column("users", "stripe_verification_id")
