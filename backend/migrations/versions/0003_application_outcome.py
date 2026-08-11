"""Application outcome tracking (pipeline board).

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_DATETIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("applications", sa.Column("outcome", sa.String(length=20), nullable=True))
    op.add_column("applications", sa.Column("outcome_updated_at", UTC_DATETIME, nullable=True))
    op.add_column("applications", sa.Column("outcome_note", sa.Text(), nullable=True))
    op.create_index("ix_applications_outcome", "applications", ["outcome"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_applications_outcome", table_name="applications")
    op.drop_column("applications", "outcome_note")
    op.drop_column("applications", "outcome_updated_at")
    op.drop_column("applications", "outcome")
