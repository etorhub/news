"""Add job_runs.trigger, source_availability_checks table, source_feeds availability columns.

Revision ID: 018
Revises: 017
Create Date: 2026-03-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_runs",
        sa.Column("trigger", sa.Text(), nullable=False, server_default="scheduled"),
    )

    op.add_column(
        "source_feeds",
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "source_feeds",
        sa.Column("last_availability_check_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "source_availability_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["feed_id"],
            ["source_feeds.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_sac_feed_checked",
        "source_availability_checks",
        ["feed_id", "checked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_sac_feed_checked", table_name="source_availability_checks")
    op.drop_table("source_availability_checks")
    op.drop_column("source_feeds", "last_availability_check_at")
    op.drop_column("source_feeds", "is_available")
    op.drop_column("job_runs", "trigger")
