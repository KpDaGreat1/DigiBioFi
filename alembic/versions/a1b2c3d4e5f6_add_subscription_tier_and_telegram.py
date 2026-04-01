"""Add subscription_tier to users and telegram to profiles

Revision ID: a1b2c3d4e5f6
Revises: b8b9f5ce7209
Create Date: 2026-03-31

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'b8b9f5ce7209'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add subscription_tier to users table
    op.add_column(
        'users',
        sa.Column('subscription_tier', sa.String(20), nullable=False, server_default='free'),
    )

    # Add telegram to profiles table
    op.add_column(
        'profiles',
        sa.Column('telegram', sa.String(500), nullable=False, server_default=''),
    )


def downgrade() -> None:
    op.drop_column('users', 'subscription_tier')
    op.drop_column('profiles', 'telegram')
