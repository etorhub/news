"""Add image_url and image_source columns to articles.

Revision ID: 012
Revises: 011
Create Date: 2026-03-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("image_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("image_source", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("articles", "image_source")
    op.drop_column("articles", "image_url")
