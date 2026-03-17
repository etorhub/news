"""Replace cluster_rewrites profile_hash with style and language.

Clean break: drop old table, create new schema keyed by (cluster_id, style, language).
Per-user rewrites are deprecated; rewrites are now shared per cluster per variant.

Revision ID: 014
Revises: 013
Create Date: 2026-03-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_cluster_rewrites_hash", table_name="cluster_rewrites")
    op.drop_table("cluster_rewrites")

    op.create_table(
        "cluster_rewrites",
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("style", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column(
            "rewrite_failed",
            sa.Boolean(),
            nullable=True,
            server_default="false",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cluster_id", "style", "language"),
    )
    op.create_index(
        "idx_cluster_rewrites_style_language",
        "cluster_rewrites",
        ["style", "language"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_cluster_rewrites_style_language", table_name="cluster_rewrites")
    op.drop_table("cluster_rewrites")

    op.create_table(
        "cluster_rewrites",
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("profile_hash", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column(
            "rewrite_failed",
            sa.Boolean(),
            nullable=True,
            server_default="false",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cluster_id", "profile_hash"),
    )
    op.create_index(
        "idx_cluster_rewrites_hash",
        "cluster_rewrites",
        ["profile_hash"],
        unique=False,
    )
