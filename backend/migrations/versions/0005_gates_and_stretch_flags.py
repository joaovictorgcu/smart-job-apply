"""Score gates on jobs and stretch flags on tailored resumes.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Server default '[]' so pre-existing rows read back as empty lists, not NULL.
    op.add_column(
        "jobs",
        sa.Column("score_gates", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "tailored_resumes",
        sa.Column("stretch_flags", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("tailored_resumes", "stretch_flags")
    op.drop_column("jobs", "score_gates")
