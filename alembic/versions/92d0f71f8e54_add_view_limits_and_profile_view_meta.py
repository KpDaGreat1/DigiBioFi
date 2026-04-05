"""add view limits and profile view metadata

Revision ID: 92d0f71f8e54
Revises: 412033653053
Create Date: 2026-04-04 14:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "92d0f71f8e54"
down_revision: Union[str, None] = "412033653053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("users", "daily_profile_views"):
        op.add_column(
            "users",
            sa.Column("daily_profile_views", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column("users", "last_view_reset"):
        op.add_column(
            "users",
            sa.Column("last_view_reset", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column("profile_views", "viewer_ip"):
        op.add_column(
            "profile_views",
            sa.Column("viewer_ip", sa.String(length=64), nullable=False, server_default=""),
        )
    if not _has_column("profile_views", "user_agent"):
        op.add_column(
            "profile_views",
            sa.Column("user_agent", sa.String(length=500), nullable=False, server_default=""),
        )


def downgrade() -> None:
    if _has_column("profile_views", "user_agent"):
        op.drop_column("profile_views", "user_agent")
    if _has_column("profile_views", "viewer_ip"):
        op.drop_column("profile_views", "viewer_ip")
    if _has_column("users", "last_view_reset"):
        op.drop_column("users", "last_view_reset")
    if _has_column("users", "daily_profile_views"):
        op.drop_column("users", "daily_profile_views")
