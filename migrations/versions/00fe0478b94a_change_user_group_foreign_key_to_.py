"""change user group foreign key to restrict

Revision ID: 00fe0478b94a
Revises: 5aba9ce90415
Create Date: 2026-11-13 18:20:00.710322
"""

from collections.abc import Sequence

from alembic import op

revision: str = "00fe0478b94a"
down_revision: str | Sequence[str] | None = "5aba9ce90415"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("users_group_id_fkey"),
        "users",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("users_group_id_fkey"),
        "users",
        "user_groups",
        ["group_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("users_group_id_fkey"),
        "users",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("users_group_id_fkey"),
        "users",
        "user_groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )
