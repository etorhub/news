"""Change server_default for rewrite_tone to Neutral journalistic style.

Revision ID: 011
Revises: 010
Create Date: 2026-03-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_DEFAULT = (
    "Journalistic style. Formal and well-written. Do not simplify; "
    "preserve original complexity and nuance. Avoid spoilers in headlines or summaries."
)
_OLD_DEFAULT = "Short sentences. Simple vocabulary. No jargon."


def upgrade() -> None:
    op.alter_column(
        "user_profiles",
        "rewrite_tone",
        existing_type=sa.Text(),
        server_default=_NEW_DEFAULT,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "user_profiles",
        "rewrite_tone",
        existing_type=sa.Text(),
        server_default=_OLD_DEFAULT,
        existing_nullable=False,
    )
