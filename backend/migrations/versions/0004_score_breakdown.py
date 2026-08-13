"""Per-dimension score breakdown on jobs.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Server default '[]' so rows scored before this migration read back as an
    # empty list rather than NULL, which the ORM would hand to the API as None.
    op.add_column(
        "jobs",
        sa.Column("score_breakdown", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("jobs", "score_breakdown")
