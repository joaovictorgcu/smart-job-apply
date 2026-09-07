"""The score's history, and a posting that can go stale.

`jobs.score` is the latest verdict and stays that way — listing filters and the
default ordering run off it. `job_scores` is every verdict, appended and never
updated, with the dimensions as queryable rows instead of JSON buried in
`ai_analyses.result`. That is what makes "62 to 81 after you added Kubernetes"
showable, and what a calibration against real interview outcomes needs.

No backfill: the scores already stored have no timestamp of their own, no model
attribution and no profile fingerprint, so inventing rows for them would put
fabricated history behind a real number. The history starts empty and fills in
from the next scoring pass.

`jobs.deadline` and `jobs.expired_at` are nullable for the same reason — nothing
truthful is known about existing rows, and null reads correctly as "still open".

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("overall", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("gates", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("depth", sa.String(length=10), nullable=False),
        sa.Column("profile_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_scores_job_id", "job_scores", ["job_id"], unique=False)
    op.create_index("ix_job_scores_user_id", "job_scores", ["user_id"], unique=False)
    op.create_index("ix_job_scores_created_at", "job_scores", ["created_at"], unique=False)
    # The one query this table exists for: one job's verdicts in order.
    op.create_index("ix_job_score_job_created", "job_scores", ["job_id", "created_at"])

    op.add_column("jobs", sa.Column("deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "expired_at")
    op.drop_column("jobs", "deadline")

    op.drop_index("ix_job_score_job_created", table_name="job_scores")
    op.drop_index("ix_job_scores_created_at", table_name="job_scores")
    op.drop_index("ix_job_scores_user_id", table_name="job_scores")
    op.drop_index("ix_job_scores_job_id", table_name="job_scores")
    op.drop_table("job_scores")
