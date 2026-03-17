"""Drop filter_negative from user_profiles.

Remove the negative news filter option and its column.

Revision ID: 016
Revises: 015
Create Date: 2026-03-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("user_profiles", "filter_negative")


def downgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("filter_negative", sa.Boolean(), nullable=False, server_default="false"),
    )
