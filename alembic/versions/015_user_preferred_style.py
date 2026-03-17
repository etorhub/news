"""Add preferred_style to user_profiles for cluster-level rewrite selection.

Replaces rewrite_tone for feed selection. Values: neutral, simple.

Revision ID: 015
Revises: 014
Create Date: 2026-03-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("preferred_style", sa.Text(), nullable=True),
    )
    # Backfill: map rewrite_tone to preferred_style
    op.execute(
        """
        UPDATE user_profiles
        SET preferred_style = CASE
            WHEN rewrite_tone ILIKE '%Short sentences%'
                 OR rewrite_tone ILIKE '%Simple%'
                 OR rewrite_tone ILIKE '%Very short%'
                 OR rewrite_tone ILIKE '%Calm%'
                 OR rewrite_tone ILIKE '%Formal%'
            THEN 'simple'
            ELSE 'neutral'
        END
        """
    )
    op.alter_column(
        "user_profiles",
        "preferred_style",
        nullable=False,
        server_default="neutral",
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "preferred_style")
