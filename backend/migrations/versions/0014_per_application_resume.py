"""The document-shaped half of the per-application resume.

This is the third of three parallel takes on the tailored-resume feature, all
of which are on main. It arrived declaring revision "0012" off "0011", exactly
like the other two, so it is chained 0012 -> 0013 -> 0014 instead.

Reduced to what 0013 did not already add, because both migrations touch the
same two tables and a column declared twice fails the upgrade outright:

* `profiles` already gained `experiences`, `projects`, `education` and
  `certifications` in 0013. Only `technologies` is left here.
* `tailored_resumes` already gained `sections`, `focus`, `base_snapshot` and
  `strategy` in 0013. What is left is `document`, `base_document`,
  `document_changes` and `document_source`.

`focus` is the one genuine disagreement between the two: 0013 declares it a
JSON object, this branch wanted a JSON array. 0013's shape stands, since its
models are the ones in the merged tree; nothing reads the column with the other
shape.

No backfill, deliberately — carried over from the original migration's
reasoning. An existing row was produced by the AI path from `resume_text`
alone: it has no structured base to snapshot and no matched terms to report,
and inventing either would put fabricated provenance behind a document a human
already reviewed. Empty defaults read correctly as "derived before this
existed".

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Added NOT NULL with a server default so an existing row reads as an empty
# list/object rather than as NULL: every consumer treats "no structured resume"
# as empty, and one nullable JSON column would make that two states to handle.
_PROFILE_COLUMNS: tuple[tuple[str, str], ...] = (("technologies", "'[]'"),)

_RESUME_COLUMNS: tuple[tuple[str, str], ...] = (
    ("document", "'{}'"),
    ("base_document", "'{}'"),
    ("document_changes", "'[]'"),
)


def upgrade() -> None:
    # batch_alter_table because SQLite cannot ALTER a column in place, and the
    # default deployment is SQLite.
    with op.batch_alter_table("profiles") as batch:
        for column, default in _PROFILE_COLUMNS:
            batch.add_column(
                sa.Column(column, sa.JSON(), nullable=False, server_default=sa.text(default))
            )

    with op.batch_alter_table("tailored_resumes") as batch:
        for column, default in _RESUME_COLUMNS:
            batch.add_column(
                sa.Column(column, sa.JSON(), nullable=False, server_default=sa.text(default))
            )
        # Every row that predates this column came from the AI endpoint, so
        # "ai" is the accurate value for it rather than a placeholder.
        batch.add_column(
            sa.Column(
                "document_source",
                sa.String(20),
                nullable=False,
                server_default=sa.text("'ai'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("tailored_resumes") as batch:
        batch.drop_column("document_source")
        for column, _default in reversed(_RESUME_COLUMNS):
            batch.drop_column(column)

    with op.batch_alter_table("profiles") as batch:
        for column, _default in reversed(_PROFILE_COLUMNS):
            batch.drop_column(column)
