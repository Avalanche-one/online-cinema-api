"""Accounts migration

Revision ID: 2115641c9a96
Revises: 00fe0478b94a
Create Date: 2026-11-13 16:43:49.002924

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from online_cinema_api.db.models.accounts import UserGroupEnum

# revision identifiers, used by Alembic.
revision: str = "2115641c9a96"
down_revision: str | Sequence[str] | None = "00fe0478b94a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    user_groups_table = sa.table(
        "user_groups",
        sa.column("id", sa.Integer),
        sa.column(
            "name", sa.Enum(UserGroupEnum, name="usergroupenum", native_enum=True)
        ),
    )

    op.bulk_insert(
        user_groups_table,
        [
            {"name": UserGroupEnum.USER.value},
            {"name": UserGroupEnum.MODERATOR.value},
            {"name": UserGroupEnum.ADMIN.value},
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        f"DELETE FROM user_groups WHERE name IN ('{UserGroupEnum.USER.value}', '{UserGroupEnum.MODERATOR.value}', '{UserGroupEnum.ADMIN.value}');"
    )