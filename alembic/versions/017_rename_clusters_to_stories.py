"""Rename clusters to stories: tables, columns, constraints, indexes.

clusters -> stories
cluster_articles -> story_articles (cluster_id -> story_id)
cluster_rewrites -> story_rewrites (cluster_id -> story_id)
user_read_clusters -> user_read_stories (cluster_id -> story_id)

Add centroid_embedding (JSONB) and needs_rewrite (BOOLEAN) to stories for
incremental assignment and value-based recomputation.

Revision ID: 017
Revises: 016
Create Date: 2026-03-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Rename clusters -> stories
    op.rename_table("clusters", "stories")

    # 2. Add new columns to stories (before renaming cluster_articles)
    op.add_column(
        "stories",
        sa.Column("centroid_embedding", JSONB(), nullable=True),
    )
    op.add_column(
        "stories",
        sa.Column(
            "needs_rewrite",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # 3. Rename cluster_articles -> story_articles
    op.rename_table("cluster_articles", "story_articles")
    op.drop_constraint(
        "cluster_articles_cluster_id_fkey",
        "story_articles",
        type_="foreignkey",
    )
    op.drop_constraint(
        "cluster_articles_pkey",
        "story_articles",
        type_="primary",
    )
    op.alter_column(
        "story_articles",
        "cluster_id",
        new_column_name="story_id",
    )
    op.create_primary_key(
        "story_articles_pkey",
        "story_articles",
        ["story_id", "article_id"],
    )
    op.create_foreign_key(
        "story_articles_story_id_fkey",
        "story_articles",
        "stories",
        ["story_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("idx_cluster_articles_cluster", table_name="story_articles")
    op.create_index(
        "idx_story_articles_story",
        "story_articles",
        ["story_id"],
        unique=False,
    )

    # 4. Rename cluster_rewrites -> story_rewrites
    op.rename_table("cluster_rewrites", "story_rewrites")
    op.drop_constraint(
        "cluster_rewrites_cluster_id_fkey",
        "story_rewrites",
        type_="foreignkey",
    )
    op.drop_constraint(
        "cluster_rewrites_pkey",
        "story_rewrites",
        type_="primary",
    )
    op.alter_column(
        "story_rewrites",
        "cluster_id",
        new_column_name="story_id",
    )
    op.create_primary_key(
        "story_rewrites_pkey",
        "story_rewrites",
        ["story_id", "style", "language"],
    )
    op.create_foreign_key(
        "story_rewrites_story_id_fkey",
        "story_rewrites",
        "stories",
        ["story_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("idx_cluster_rewrites_style_language", table_name="story_rewrites")
    op.create_index(
        "idx_story_rewrites_style_language",
        "story_rewrites",
        ["style", "language"],
        unique=False,
    )

    # 5. Rename user_read_clusters -> user_read_stories
    op.rename_table("user_read_clusters", "user_read_stories")
    op.drop_constraint(
        "user_read_clusters_cluster_id_fkey",
        "user_read_stories",
        type_="foreignkey",
    )
    op.drop_constraint(
        "user_read_clusters_pkey",
        "user_read_stories",
        type_="primary",
    )
    op.alter_column(
        "user_read_stories",
        "cluster_id",
        new_column_name="story_id",
    )
    op.create_primary_key(
        "user_read_stories_pkey",
        "user_read_stories",
        ["user_id", "story_id"],
    )
    op.create_foreign_key(
        "user_read_stories_story_id_fkey",
        "user_read_stories",
        "stories",
        ["story_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("idx_user_read_clusters_user", table_name="user_read_stories")
    op.create_index(
        "idx_user_read_stories_user",
        "user_read_stories",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    # Reverse in opposite order

    # 5. user_read_stories -> user_read_clusters
    op.drop_index("idx_user_read_stories_user", table_name="user_read_stories")
    op.drop_constraint("user_read_stories_story_id_fkey", "user_read_stories", type_="foreignkey")
    op.drop_constraint("user_read_stories_pkey", "user_read_stories", type_="primary")
    op.alter_column(
        "user_read_stories",
        "story_id",
        new_column_name="cluster_id",
    )
    op.create_primary_key(
        "user_read_clusters_pkey",
        "user_read_stories",
        ["user_id", "cluster_id"],
    )
    op.create_foreign_key(
        "user_read_clusters_cluster_id_fkey",
        "user_read_stories",
        "stories",
        ["cluster_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_user_read_clusters_user",
        "user_read_stories",
        ["user_id"],
        unique=False,
    )
    op.rename_table("user_read_stories", "user_read_clusters")

    # 4. story_rewrites -> cluster_rewrites
    op.drop_index("idx_story_rewrites_style_language", table_name="story_rewrites")
    op.drop_constraint("story_rewrites_story_id_fkey", "story_rewrites", type_="foreignkey")
    op.drop_constraint("story_rewrites_pkey", "story_rewrites", type_="primary")
    op.alter_column(
        "story_rewrites",
        "story_id",
        new_column_name="cluster_id",
    )
    op.create_primary_key(
        "cluster_rewrites_pkey",
        "story_rewrites",
        ["cluster_id", "style", "language"],
    )
    op.create_foreign_key(
        "cluster_rewrites_cluster_id_fkey",
        "story_rewrites",
        "stories",
        ["cluster_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_cluster_rewrites_style_language",
        "story_rewrites",
        ["style", "language"],
        unique=False,
    )
    op.rename_table("story_rewrites", "cluster_rewrites")

    # 3. story_articles -> cluster_articles
    op.drop_index("idx_story_articles_story", table_name="story_articles")
    op.drop_constraint("story_articles_story_id_fkey", "story_articles", type_="foreignkey")
    op.drop_constraint("story_articles_pkey", "story_articles", type_="primary")
    op.alter_column(
        "story_articles",
        "story_id",
        new_column_name="cluster_id",
    )
    op.create_primary_key(
        "cluster_articles_pkey",
        "story_articles",
        ["cluster_id", "article_id"],
    )
    op.create_foreign_key(
        "cluster_articles_cluster_id_fkey",
        "story_articles",
        "stories",
        ["cluster_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "idx_cluster_articles_cluster",
        "story_articles",
        ["cluster_id"],
        unique=False,
    )
    op.rename_table("story_articles", "cluster_articles")

    # 2. Drop new columns from stories
    op.drop_column("stories", "needs_rewrite")
    op.drop_column("stories", "centroid_embedding")

    # 1. stories -> clusters
    op.rename_table("stories", "clusters")
