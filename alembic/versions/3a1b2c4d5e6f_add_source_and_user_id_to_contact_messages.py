"""add_source_and_user_id_to_contact_messages

Revision ID: 3a1b2c4d5e6f
Revises: ffc203b3b4b3
Create Date: 2026-04-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a1b2c4d5e6f'
down_revision: Union[str, None] = 'f90d5824709c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode for schema changes.
    # user_id column: nullable Integer (FK to users.id — enforced at app level)
    with op.batch_alter_table('contact_messages') as batch_op:
        batch_op.add_column(
            sa.Column('user_id', sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('source', sa.String(length=20), nullable=False, server_default='external')
        )
    op.create_index('ix_contact_messages_user_id', 'contact_messages', ['user_id'], unique=False)
    op.create_index('ix_contact_messages_source', 'contact_messages', ['source'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_contact_messages_source', table_name='contact_messages')
    op.drop_index('ix_contact_messages_user_id', table_name='contact_messages')
    with op.batch_alter_table('contact_messages') as batch_op:
        batch_op.drop_column('source')
        batch_op.drop_column('user_id')



