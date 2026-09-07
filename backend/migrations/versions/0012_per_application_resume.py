"""The master resume gains structure, and each application gains its own version.

Two halves of one feature.

`profiles` gets `technologies`, `experiences`, `projects`, `education` and
`certifications`. The free-text `resume_text` stays exactly where it is and
stays what the AI path reads; the structured lists are what let a derivation
reorder and re-describe real entries instead of reflowing a blob of prose.

`tailored_resumes` gets `document`, `base_document`, `focus`,
`document_changes` and `document_source`. The first is the resume one
application presents, the second is the master as it stood when that version
was derived — which is the isolation guarantee: editing the profile afterwards
cannot reach back into an application that already has its own version.

No backfill, deliberately. An existing row was produced by the AI path from
`resume_text` alone: it has no structured base to snapshot and no matched terms
to report, and inventing either would put fabricated provenance behind a
document a human already reviewed. Empty defaults read correctly as "derived
before this existed", which is what the API reports and what the UI renders
from `content` alone.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Added NOT NULL with a server default so an existing row reads as an empty
# list/object rather than as NULL: every consumer treats "no structured resume"
# as empty, and one nullable JSON column would make that two states to handle.
_PROFILE_LIST_COLUMNS = ("technologies", "experiences", "projects", "education")


def upgrade() -> None:
    for column in _PROFILE_LIST_COLUMNS:
        op.add_column(
            "profiles",
            sa.Column(column, sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
    op.add_column(
        "profiles",
        sa.Column("certifications", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )

    op.add_column(
        "tailored_resumes",
        sa.Column("document", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "tailored_resumes",
        sa.Column("base_document", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "tailored_resumes",
        sa.Column("focus", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "tailored_resumes",
        sa.Column("document_changes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "tailored_resumes",
        sa.Column(
            "document_source",
            sa.String(length=20),
            nullable=False,
            server_default="rules",
        ),
    )


def downgrade() -> None:
    op.drop_column("tailored_resumes", "document_source")
    op.drop_column("tailored_resumes", "document_changes")
    op.drop_column("tailored_resumes", "focus")
    op.drop_column("tailored_resumes", "base_document")
    op.drop_column("tailored_resumes", "document")

    op.drop_column("profiles", "certifications")
    for column in reversed(_PROFILE_LIST_COLUMNS):
        op.drop_column("profiles", column)
