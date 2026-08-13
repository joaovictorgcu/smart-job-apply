"""Job source portal.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every pre-existing job came from LinkedIn, so the default backfills truthfully.
    op.add_column(
        "jobs",
        sa.Column("source", sa.String(length=30), nullable=False, server_default="linkedin"),
    )
    op.create_index("ix_jobs_source", "jobs", ["source"])


def downgrade() -> None:
    op.drop_index("ix_jobs_source", table_name="jobs")
    op.drop_column("jobs", "source")
