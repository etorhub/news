"""Add rewrite_requests table for on-demand rewrite queue.

Revision ID: 009
Revises: 008
Create Date: 2025-03-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rewrite_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_rewrite_requests_status",
        "rewrite_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_rewrite_requests_user_id_status",
        "rewrite_requests",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_rewrite_requests_user_id_status", table_name="rewrite_requests")
    op.drop_index("idx_rewrite_requests_status", table_name="rewrite_requests")
    op.drop_table("rewrite_requests")
