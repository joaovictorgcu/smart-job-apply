"""Which door an application goes out of: Easy Apply, or the company's own site.

Portal jobs (Gupy and the ones after it) have no Easy Apply form, so their
applications are prepared here and sent by the user on the company's page. The
column marks that difference so the two completion paths can be kept apart —
and so an application made by hand finally counts in the pipeline and the stats.

Existing rows were all LinkedIn Easy Apply drafts, so the server default
backfills them truthfully rather than leaving a nullable column nobody can read.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "channel",
            sa.String(length=20),
            nullable=False,
            server_default="easy_apply",
        ),
    )
    op.create_index("ix_applications_channel", "applications", ["channel"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_applications_channel", table_name="applications")
    op.drop_column("applications", "channel")
