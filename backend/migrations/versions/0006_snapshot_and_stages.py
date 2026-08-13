"""Submission snapshot on applications and interview stages.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_DATETIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    # Nullable on purpose: null distinguishes "submitted before this feature"
    # from an empty snapshot.
    op.add_column("applications", sa.Column("submitted_snapshot", sa.JSON(), nullable=True))

    op.create_table(
        "interview_stages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_type", sa.String(length=30), nullable=False),
        sa.Column("scheduled_at", UTC_DATETIME, nullable=True),
        sa.Column("completed_at", UTC_DATETIME, nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", UTC_DATETIME, nullable=False),
        sa.Column("updated_at", UTC_DATETIME, nullable=False),
    )
    op.create_index("ix_interview_stages_user_id", "interview_stages", ["user_id"])
    op.create_index("ix_interview_stages_application_id", "interview_stages", ["application_id"])
    op.create_index(
        "ix_stage_application", "interview_stages", ["application_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_stage_application", table_name="interview_stages")
    op.drop_index("ix_interview_stages_application_id", table_name="interview_stages")
    op.drop_index("ix_interview_stages_user_id", table_name="interview_stages")
    op.drop_table("interview_stages")
    op.drop_column("applications", "submitted_snapshot")
