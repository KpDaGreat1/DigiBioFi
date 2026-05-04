"""enforce_user_role_constraint

Revision ID: b7c4d2e1f9a8
Revises: a9f4b1c2d3e4
Create Date: 2026-05-01 22:40:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7c4d2e1f9a8"
down_revision: Union[str, None] = "a9f4b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_VALID_ROLES = ("admin", "business", "freelancer", "user")


def upgrade() -> None:
    op.execute("UPDATE users SET role = lower(trim(coalesce(role, 'user')))")
    invalid_roles = ", ".join(f"'{role}'" for role in _VALID_ROLES)
    op.execute(
        f"UPDATE users SET role = 'user' WHERE role NOT IN ({invalid_roles})"
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            "ck_users_role_valid",
            "role IN ('admin', 'business', 'freelancer', 'user')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role_valid", type_="check")
