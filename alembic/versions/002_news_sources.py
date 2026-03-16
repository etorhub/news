"""Add news_sources, source_feeds, source_discovery_log tables.

Revision ID: 002
Revises: 001
Create Date: 2025-03-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_sources",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("homepage_url", sa.Text(), nullable=False),
        sa.Column("country_code", sa.CHAR(2), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("languages", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("quality_score", sa.DECIMAL(5, 2), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "full_text_available",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("last_checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.create_index("idx_ns_country", "news_sources", ["country_code"], unique=False)
    op.create_index(
        "idx_ns_region",
        "news_sources",
        ["country_code", "region"],
        unique=False,
    )
    op.create_index(
        "idx_ns_quality",
        "news_sources",
        ["quality_score"],
        unique=False,
        postgresql_ops={"quality_score": "DESC"},
    )

    op.create_table(
        "source_feeds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("feed_type", sa.Text(), nullable=False),
        sa.Column("feed_url", sa.Text(), nullable=False),
        sa.Column("feed_label", sa.Text(), nullable=True),
        sa.Column(
            "poll_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column("last_fetched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_item_guid", sa.Text(), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("avg_articles_per_day", sa.DECIMAL(6, 2), nullable=True),
        sa.Column("feed_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["news_sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sf_source", "source_feeds", ["source_id"], unique=False)
    op.create_index(
        "idx_sf_poll",
        "source_feeds",
        ["last_fetched_at"],
        unique=False,
        postgresql_where=sa.text("feed_active = true"),
    )

    op.create_table(
        "source_discovery_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("discovery_run_id", sa.Text(), nullable=False),
        sa.Column("target_location", JSONB(), nullable=False),
        sa.Column("discovery_method", sa.Text(), nullable=True),
        sa.Column("validation_result", JSONB(), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["news_sources.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("source_discovery_log")
    op.drop_index("idx_sf_poll", table_name="source_feeds")
    op.drop_index("idx_sf_source", table_name="source_feeds")
    op.drop_table("source_feeds")
    op.drop_index("idx_ns_quality", table_name="news_sources")
    op.drop_index("idx_ns_region", table_name="news_sources")
    op.drop_index("idx_ns_country", table_name="news_sources")
    op.drop_table("news_sources")
