"""The structured master resume, and one adapted snapshot per application.

`experiences` is the master resume decomposed — company, role, period,
responsibilities, technologies, projects, results — because the per-application
derivation has to reason about the parts separately. A posting asking for
PostgreSQL must be able to promote the one bullet that mentions it, which is
impossible while the whole history is a single text blob.

`application_resumes` is unique on `application_id`: one document per
application, held as a **full snapshot**. Nothing is a foreign-key view onto the
master, so a later master edit cannot reach a document a human has already
reviewed, and editing one application's document cannot reach a sibling's. That
isolation is the feature's central promise, and a snapshot is the only way to
make it structural instead of a convention.

No backfill for applications that already exist. There is no honest snapshot to
invent for them: the master resume of the day they were prepared is not
recoverable, and fabricating one from today's would claim a document was
reviewed that never existed. They read as "not adapted yet" and offer the user
the action, which is true.

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


def upgrade() -> None:
    op.create_table(
        "experiences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=200), nullable=False),
        sa.Column("employment_type", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.JSON(), nullable=False),
        sa.Column("technologies", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("projects", sa.JSON(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiences_user_id", "experiences", ["user_id"], unique=False)
    # The one query the master resume page makes: this user's positions, in order.
    op.create_index("ix_experience_user_position", "experiences", ["user_id", "position"])

    op.create_table(
        "application_resumes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("headline", sa.String(length=300), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("highlighted_skills", sa.JSON(), nullable=False),
        sa.Column("emphasized_technologies", sa.JSON(), nullable=False),
        sa.Column("experiences", sa.JSON(), nullable=False),
        sa.Column("projects", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("fit_factors", sa.JSON(), nullable=False),
        sa.Column("uncovered_requirements", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("was_edited", sa.Boolean(), nullable=False),
        sa.Column("adapted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="uq_application_resume_application"),
    )
    op.create_index(
        "ix_application_resumes_user_id", "application_resumes", ["user_id"], unique=False
    )
    op.create_index(
        "ix_application_resumes_application_id",
        "application_resumes",
        ["application_id"],
        unique=True,
    )
    op.create_index("ix_application_resumes_job_id", "application_resumes", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_application_resumes_job_id", table_name="application_resumes")
    op.drop_index("ix_application_resumes_application_id", table_name="application_resumes")
    op.drop_index("ix_application_resumes_user_id", table_name="application_resumes")
    op.drop_table("application_resumes")

    op.drop_index("ix_experience_user_position", table_name="experiences")
    op.drop_index("ix_experiences_user_id", table_name="experiences")
    op.drop_table("experiences")
