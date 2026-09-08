"""The master resume gains structure, and each application gains its own version.

Two halves of one feature.

`profiles` gets `experiences`, `projects`, `education` and `certifications`. The
free-text `resume_text` stays exactly where it is and stays authoritative for the
AI path and the invention guard; the structured lists are what let a derivation
reorder and re-describe real entries instead of reflowing a blob of prose.

`tailored_resumes` gets `sections`, `focus`, `base_snapshot` and `strategy`. The
first two are the derived, per-application resume and the reason it looks the way
it does. `base_snapshot` is the isolation guarantee: the master exactly as it
stood when this version was derived, so editing the profile afterwards can never
reach back into an application that already has its own version.

No backfill anywhere. An existing row was produced by the AI path from
`resume_text` alone: it has no structured base to snapshot and no matched
keywords to report, and inventing either would put fabricated provenance behind
a document a human already reviewed. Empty defaults read correctly as "derived
before this existed" â€” which is what the API reports, and what the UI renders
from `content` alone.

Revision ID: 0013
Revises: 0011
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Added NOT NULL with a server default so existing rows read back as an empty
# collection rather than as None, which every consumer would otherwise guard.
# The ORM keeps writing its own default on insert.
_PROFILE_LISTS = ("experiences", "projects", "education", "certifications")


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        for column in _PROFILE_LISTS:
            batch.add_column(
                sa.Column(column, sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
            )

    with op.batch_alter_table("tailored_resumes") as batch:
        batch.add_column(
            sa.Column("sections", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch.add_column(
            sa.Column("focus", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch.add_column(
            sa.Column("base_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'"))
        )
        batch.add_column(
            sa.Column(
                "strategy",
                sa.String(length=20),
                nullable=False,
                # Every row that predates this column came from the AI endpoint,
                # which is what "ai" means here â€” a fact about them, not a guess.
                server_default="ai",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("tailored_resumes") as batch:
        for column in ("strategy", "base_snapshot", "focus", "sections"):
            batch.drop_column(column)

    with op.batch_alter_table("profiles") as batch:
        for column in reversed(_PROFILE_LISTS):
            batch.drop_column(column)
