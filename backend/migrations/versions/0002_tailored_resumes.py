"""Tailored resumes: per-job CV adaptations.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `UtcDateTime` in app.database.base is a TypeDecorator over
# DateTime(timezone=True), so that is what the DDL must use.
UTC_DATETIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "tailored_resumes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("unsupported_requirements", sa.JSON(), nullable=False),
        sa.Column("invention_flags", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("was_edited", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_tailored_resume_job"),
    )
    op.create_index(
        "ix_tailored_resumes_user_id", "tailored_resumes", ["user_id"], unique=False
    )
    op.create_index(
        "ix_tailored_resumes_job_id", "tailored_resumes", ["job_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_tailored_resumes_job_id", table_name="tailored_resumes")
    op.drop_index("ix_tailored_resumes_user_id", table_name="tailored_resumes")
    op.drop_table("tailored_resumes")
