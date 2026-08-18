"""Fingerprint of the reviewed Easy Apply form.

Submission re-opens the posting and compares the form it finds against the hash
recorded when the user reviewed it. Existing rows stay NULL: they were prepared
before the check existed, so there is nothing truthful to backfill and they are
refused rather than sent against an unverified form.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("form_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("applications", "form_fingerprint")
