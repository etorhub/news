"""Initial schema: users, user_profiles, user_sources, user_topics, articles, rewrites.

Revision ID: 001
Revises:
Create Date: 2025-03-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=False, server_default="ca"),
        sa.Column(
            "filter_negative",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "rewrite_tone",
            sa.Text(),
            nullable=False,
            server_default="Short sentences. Simple vocabulary. No jargon.",
        ),
        sa.Column(
            "high_contrast",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "user_sources",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "source_id"),
    )
    op.create_table(
        "user_topics",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "topic_id"),
    )
    op.create_table(
        "articles",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rewrites",
        sa.Column("article_id", sa.Text(), nullable=False),
        sa.Column("profile_hash", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("article_id", "profile_hash"),
    )
    op.create_index("idx_articles_source", "articles", ["source_id"], unique=False)
    op.create_index(
        "idx_articles_published",
        "articles",
        ["published_at"],
        unique=False,
    )
    op.create_index("idx_rewrites_hash", "rewrites", ["profile_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_rewrites_hash", table_name="rewrites")
    op.drop_index("idx_articles_published", table_name="articles")
    op.drop_index("idx_articles_source", table_name="articles")
    op.drop_table("rewrites")
    op.drop_table("articles")
    op.drop_table("user_topics")
    op.drop_table("user_sources")
    op.drop_table("user_profiles")
    op.drop_table("users")
