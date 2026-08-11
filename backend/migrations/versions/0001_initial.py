"""Initial schema: users, profiles, searches, jobs, applications, automation.

Revision ID: 0001
Revises: None
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `UtcDateTime` in app.database.base is a TypeDecorator over
# DateTime(timezone=True), so that is what the DDL must use.
UTC_DATETIME = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", UTC_DATETIME, nullable=True),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("headline", sa.String(length=300), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("years_of_experience", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("resume_text", sa.Text(), nullable=True),
        sa.Column("resume_filename", sa.String(length=255), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("preferred_languages", sa.JSON(), nullable=False),
        sa.Column("answer_bank", sa.JSON(), nullable=False),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"], unique=True)

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("daily_cap", sa.Integer(), nullable=False),
        sa.Column("min_score", sa.Integer(), nullable=False),
        sa.Column("action_delay_min", sa.Float(), nullable=False),
        sa.Column("action_delay_max", sa.Float(), nullable=False),
        sa.Column("apply_delay_min", sa.Float(), nullable=False),
        sa.Column("apply_delay_max", sa.Float(), nullable=False),
        sa.Column("working_hour_start", sa.Integer(), nullable=False),
        sa.Column("working_hour_end", sa.Integer(), nullable=False),
        sa.Column("require_manual_approval", sa.Boolean(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("ai_model", sa.String(length=100), nullable=True),
        sa.Column("cover_letter_tone", sa.String(length=50), nullable=False),
        sa.Column("content_language", sa.String(length=20), nullable=False),
        sa.Column("generate_cover_letter", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)

    # Holds the encrypted LinkedIn session state. One account per user.
    op.create_table(
        "linkedin_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("encrypted_storage_state", sa.Text(), nullable=True),
        sa.Column("browser_profile_dir", sa.String(length=500), nullable=True),
        sa.Column("is_connected", sa.Boolean(), nullable=False),
        sa.Column("last_verified_at", UTC_DATETIME, nullable=True),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_linkedin_account_user"),
    )
    op.create_index("ix_linkedin_accounts_user_id", "linkedin_accounts", ["user_id"], unique=True)

    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("keywords", sa.String(length=300), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("remote_filter", sa.String(length=50), nullable=True),
        sa.Column("experience_levels", sa.JSON(), nullable=False),
        sa.Column("date_posted", sa.String(length=30), nullable=True),
        sa.Column("easy_apply_only", sa.Boolean(), nullable=False),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", UTC_DATETIME, nullable=True),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_searches_user_id", "searches", ["user_id"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("search_id", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("company", sa.String(length=300), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("workplace_type", sa.String(length=50), nullable=True),
        sa.Column("easy_apply", sa.Boolean(), nullable=False),
        sa.Column("detected_language", sa.String(length=20), nullable=True),
        sa.Column("posted_at", UTC_DATETIME, nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_reasons", sa.JSON(), nullable=False),
        sa.Column("missing_requirements", sa.JSON(), nullable=False),
        sa.Column("skip_reason", sa.String(length=300), nullable=True),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Deduplication: the same LinkedIn posting is stored once per user.
        sa.UniqueConstraint("user_id", "external_id", name="uq_job_user_external"),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"], unique=False)
    op.create_index("ix_jobs_search_id", "jobs", ["search_id"], unique=False)
    op.create_index("ix_jobs_external_id", "jobs", ["external_id"], unique=False)
    op.create_index("ix_jobs_status", "jobs", ["status"], unique=False)
    op.create_index("ix_jobs_score", "jobs", ["score"], unique=False)
    # Backs the default job listing query (a user's jobs filtered by status).
    op.create_index("ix_job_user_status", "jobs", ["user_id", "status"], unique=False)

    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("search_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("jobs_found", sa.Integer(), nullable=False),
        sa.Column("jobs_analyzed", sa.Integer(), nullable=False),
        sa.Column("jobs_skipped", sa.Integer(), nullable=False),
        sa.Column("applications_prepared", sa.Integer(), nullable=False),
        sa.Column("applications_submitted", sa.Integer(), nullable=False),
        sa.Column("stop_requested", sa.Boolean(), nullable=False),
        sa.Column("blocked_reason", sa.String(length=300), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("checkpoint", sa.JSON(), nullable=False),
        sa.Column("started_at", UTC_DATETIME, nullable=True),
        sa.Column("finished_at", UTC_DATETIME, nullable=True),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_runs_user_id", "automation_runs", ["user_id"], unique=False)
    op.create_index("ix_automation_runs_kind", "automation_runs", ["kind"], unique=False)
    op.create_index("ix_automation_runs_status", "automation_runs", ["status"], unique=False)
    # Finds the active run for a user without scanning history.
    op.create_index("ix_run_user_status", "automation_runs", ["user_id", "status"], unique=False)

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cover_letter", sa.Text(), nullable=True),
        sa.Column("screening_answers", sa.JSON(), nullable=False),
        sa.Column("resume_filename", sa.String(length=255), nullable=True),
        sa.Column("total_steps", sa.Integer(), nullable=True),
        sa.Column("current_step", sa.Integer(), nullable=True),
        sa.Column("needs_human_input", sa.Boolean(), nullable=False),
        sa.Column("was_dry_run", sa.Boolean(), nullable=False),
        sa.Column("approved_at", UTC_DATETIME, nullable=True),
        sa.Column("submitted_at", UTC_DATETIME, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # At most one application per job — no accidental double submission.
        sa.UniqueConstraint("job_id", name="uq_application_job"),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"], unique=False)
    op.create_index("ix_applications_job_id", "applications", ["job_id"], unique=True)
    op.create_index("ix_applications_status", "applications", ["status"], unique=False)

    # Append-only audit trail. `created_at` has no server default because the
    # model always supplies it (ApplicationEvent.__init__).
    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("is_error", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTC_DATETIME, nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["automation_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_events_application_id",
        "application_events",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_events_event_type", "application_events", ["event_type"], unique=False
    )
    op.create_index(
        "ix_application_events_created_at", "application_events", ["created_at"], unique=False
    )
    # Serves the chronological timeline of a single application.
    op.create_index(
        "ix_event_application_created",
        "application_events",
        ["application_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("was_refusal", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", UTC_DATETIME, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_analyses_user_id", "ai_analyses", ["user_id"], unique=False)
    op.create_index("ix_ai_analyses_job_id", "ai_analyses", ["job_id"], unique=False)
    op.create_index("ix_ai_analyses_kind", "ai_analyses", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_analyses_kind", table_name="ai_analyses")
    op.drop_index("ix_ai_analyses_job_id", table_name="ai_analyses")
    op.drop_index("ix_ai_analyses_user_id", table_name="ai_analyses")
    op.drop_table("ai_analyses")

    op.drop_index("ix_event_application_created", table_name="application_events")
    op.drop_index("ix_application_events_created_at", table_name="application_events")
    op.drop_index("ix_application_events_event_type", table_name="application_events")
    op.drop_index("ix_application_events_application_id", table_name="application_events")
    op.drop_table("application_events")

    op.drop_index("ix_applications_status", table_name="applications")
    op.drop_index("ix_applications_job_id", table_name="applications")
    op.drop_index("ix_applications_user_id", table_name="applications")
    op.drop_table("applications")

    op.drop_index("ix_run_user_status", table_name="automation_runs")
    op.drop_index("ix_automation_runs_status", table_name="automation_runs")
    op.drop_index("ix_automation_runs_kind", table_name="automation_runs")
    op.drop_index("ix_automation_runs_user_id", table_name="automation_runs")
    op.drop_table("automation_runs")

    op.drop_index("ix_job_user_status", table_name="jobs")
    op.drop_index("ix_jobs_score", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_external_id", table_name="jobs")
    op.drop_index("ix_jobs_search_id", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_searches_user_id", table_name="searches")
    op.drop_table("searches")

    op.drop_index("ix_linkedin_accounts_user_id", table_name="linkedin_accounts")
    op.drop_table("linkedin_accounts")

    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")

    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_table("profiles")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
