"""What kind of vacancy an account is looking for.

One row per user, and deliberately not columns on `profiles` or
`user_settings`. The profile says what the candidate has done; this says what
they want next, and the two move independently. `user_settings` is operational
guardrails whose defaults carry a safety promise, which these do not: getting a
preference wrong costs a bad recommendation, never an unwanted submission.

No backfill and no defaults beyond empty. An account that has not stated a
preference has not stated one — inventing "remote, mid-senior" for everybody
would silently skip postings the user never rejected, which is exactly the
failure the excluded-terms list is supposed to be an explicit opt-in to.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("target_role", sa.String(length=200), nullable=True),
        sa.Column("alternative_roles", sa.JSON(), nullable=False),
        sa.Column("seniority", sa.JSON(), nullable=False),
        sa.Column("work_models", sa.JSON(), nullable=False),
        sa.Column("locations", sa.JSON(), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=10), nullable=False),
        sa.Column("priority_technologies", sa.JSON(), nullable=False),
        sa.Column("excluded_terms", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_job_preferences_user_id", "job_preferences", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_job_preferences_user_id", table_name="job_preferences")
    op.drop_table("job_preferences")
