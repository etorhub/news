"""Add clusters, cluster_articles, cluster_rewrites, articles.embedding.

Revision ID: 004
Revises: 003
Create Date: 2025-03-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("embedding", JSONB(), nullable=True),
    )

    op.create_table(
        "clusters",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "cluster_articles",
        sa.Column("cluster_id", UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["clusters.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cluster_id", "article_id"),
    )

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
        "idx_cluster_articles_cluster",
        "cluster_articles",
        ["cluster_id"],
        unique=False,
    )
    op.create_index(
        "idx_cluster_rewrites_hash",
        "cluster_rewrites",
        ["profile_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_cluster_rewrites_hash", table_name="cluster_rewrites")
    op.drop_index("idx_cluster_articles_cluster", table_name="cluster_articles")
    op.drop_table("cluster_rewrites")
    op.drop_table("cluster_articles")
    op.drop_table("clusters")
    op.drop_column("articles", "embedding")
