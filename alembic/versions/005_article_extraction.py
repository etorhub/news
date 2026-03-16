"""Add extraction_status, extraction_method, extracted_at to articles.

Revision ID: 005
Revises: 004
Create Date: 2025-03-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("extraction_status", sa.Text(), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column("extraction_method", sa.Text(), nullable=True),
    )
    op.add_column(
        "articles",
        sa.Column(
            "extracted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # Backfill: full_text present and non-empty -> extracted/rss, else -> pending
    op.execute(
        """
        UPDATE articles
        SET extraction_status = 'extracted', extraction_method = 'rss'
        WHERE full_text IS NOT NULL AND length(trim(full_text)) > 0
        """
    )
    op.execute(
        """
        UPDATE articles
        SET extraction_status = 'pending'
        WHERE extraction_status IS NULL
        """
    )

    op.alter_column(
        "articles",
        "extraction_status",
        nullable=False,
        server_default=sa.text("'pending'"),
    )
    op.alter_column(
        "articles",
        "extraction_method",
        nullable=True,
    )

    op.create_index(
        "idx_articles_extraction_status",
        "articles",
        ["extraction_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_articles_extraction_status", table_name="articles")
    op.drop_column("articles", "extracted_at")
    op.drop_column("articles", "extraction_method")
    op.drop_column("articles", "extraction_status")
