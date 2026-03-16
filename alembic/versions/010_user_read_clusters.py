"""Add user_read_clusters table for per-user read tracking.

Revision ID: 010
Revises: 009
Create Date: 2025-03-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_read_clusters",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("cluster_id", sa.UUID(), nullable=False),
        sa.Column(
            "read_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["clusters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "cluster_id"),
    )
    op.create_index(
        "idx_user_read_clusters_user",
        "user_read_clusters",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_user_read_clusters_user", table_name="user_read_clusters")
    op.drop_table("user_read_clusters")
