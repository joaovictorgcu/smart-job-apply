"""Search, job, application, application events and AI analyses."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.models.enums import (
    AnalysisKind,
    ApplicationEventType,
    ApplicationOutcome,
    ApplicationStatus,
    JobStatus,
)

if TYPE_CHECKING:
    from app.models.automation import AutomationRun
    from app.models.user import User


class Search(Base, TimestampMixin):
    """A saved, reusable set of filters."""

    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(200))
    keywords: Mapped[str] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    # remote/hybrid/onsite
    remote_filter: Mapped[str | None] = mapped_column(String(50), default=None)
    experience_levels: Mapped[list[str]] = mapped_column(JSON, default=list)
    date_posted: Mapped[str | None] = mapped_column(String(30), default=None)  # day/week/month
    easy_apply_only: Mapped[bool] = mapped_column(Boolean, default=True)
    max_results: Mapped[int] = mapped_column(Integer, default=25)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="searches")
    jobs: Mapped[list[Job]] = relationship(back_populates="search")
    runs: Mapped[list[AutomationRun]] = relationship(back_populates="search")


class Job(Base, TimestampMixin):
    """A discovered job. Unique per (user, external id) — this enforces dedup."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "external_id", name="uq_job_user_external"),
        Index("ix_job_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    search_id: Mapped[int | None] = mapped_column(
        ForeignKey("searches.id", ondelete="SET NULL"), default=None, index=True
    )

    external_id: Mapped[str] = mapped_column(String(100), index=True)
    # Which portal the job came from ("linkedin", "gupy", ...). Discovery is
    # per-portal; the scoring/review pipeline downstream is portal-agnostic.
    source: Mapped[str] = mapped_column(String(30), default="linkedin", index=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    url: Mapped[str | None] = mapped_column(String(1000), default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    workplace_type: Mapped[str | None] = mapped_column(String(50), default=None)
    easy_apply: Mapped[bool] = mapped_column(Boolean, default=False)
    detected_language: Mapped[str | None] = mapped_column(String(20), default=None)
    posted_at: Mapped[datetime | None] = mapped_column(default=None)

    status: Mapped[JobStatus] = mapped_column(String(30), default=JobStatus.DISCOVERED, index=True)
    score: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    score_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    # [{"dimension", "score", "weight", "evidence"}] — how the overall score was
    # reached, so the number can be argued with instead of taken on faith. Empty
    # for jobs scored before this existed, and for a model that returned none.
    score_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # [{"gate", "status", "evidence"}] — decisive checks (eligibility, language)
    # evaluated before the score. A failed gate skips the job with the posting's
    # own wording as the reason, instead of a misleading low score.
    score_gates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    skip_reason: Mapped[str | None] = mapped_column(String(300), default=None)

    user: Mapped[User] = relationship(back_populates="jobs")
    search: Mapped[Search | None] = relationship(back_populates="jobs")
    application: Mapped[Application | None] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    analyses: Mapped[list[AIAnalysis]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    tailored_resume: Mapped[TailoredResume | None] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )


class Application(Base, TimestampMixin):
    """An application to a job.

    It sits in `AWAITING_REVIEW` with the form filled in until the user approves it.
    """

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", name="uq_application_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, index=True
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        String(30), default=ApplicationStatus.DRAFT, index=True
    )
    cover_letter: Mapped[str | None] = mapped_column(Text, default=None)
    # [{"question", "answer", "type", "options", "confidence", "needs_review", "field_id"}]
    screening_answers: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    resume_filename: Mapped[str | None] = mapped_column(String(255), default=None)
    total_steps: Mapped[int | None] = mapped_column(Integer, default=None)
    current_step: Mapped[int | None] = mapped_column(Integer, default=None)
    needs_human_input: Mapped[bool] = mapped_column(Boolean, default=False)
    was_dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(default=None)
    submitted_at: Mapped[datetime | None] = mapped_column(default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    # Post-submission result, tracked by the user on the pipeline board. Null until
    # the application is submitted (then it starts at APPLIED).
    outcome: Mapped[ApplicationOutcome | None] = mapped_column(String(20), default=None, index=True)
    outcome_updated_at: Mapped[datetime | None] = mapped_column(default=None)
    outcome_note: Mapped[str | None] = mapped_column(Text, default=None)

    # Frozen at submit time: the posting text (LinkedIn postings vanish quickly)
    # and the exact letter/answers that went out. Null for pre-feature rows.
    submitted_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    user: Mapped[User] = relationship(back_populates="applications")
    job: Mapped[Job] = relationship(back_populates="application")
    events: Mapped[list[ApplicationEvent]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEvent.created_at",
    )
    stages: Mapped[list[InterviewStage]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="InterviewStage.created_at",
    )


class InterviewStage(Base, TimestampMixin):
    """One interview step of a submitted application.

    Finer-grained than the board's single Interview column: a process is a
    sequence of stages (phone screen, technical, final round...), each with its
    own date and feedback.
    """

    __tablename__ = "interview_stages"
    __table_args__ = (Index("ix_stage_application", "application_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )

    # phone_screen / technical / case_study / final_round / offer_discussion
    stage_type: Mapped[str] = mapped_column(String(30))
    scheduled_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    application: Mapped[Application] = relationship(back_populates="stages")


class ApplicationEvent(Base):
    """Append-only trail of what happened in each application.

    This is what makes a bug debuggable: every form step, every answered question
    and every error is recorded with its timestamp and details.
    """

    __tablename__ = "application_events"
    __table_args__ = (Index("ix_event_application_created", "application_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_runs.id", ondelete="SET NULL"), default=None
    )

    event_type: Mapped[ApplicationEventType] = mapped_column(String(40), index=True)
    message: Mapped[str | None] = mapped_column(Text, default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=None, index=True)

    application: Mapped[Application] = relationship(back_populates="events")

    def __init__(self, **kwargs: Any) -> None:
        from app.database.base import utcnow

        kwargs.setdefault("created_at", utcnow())
        super().__init__(**kwargs)


class AIAnalysis(Base, TimestampMixin):
    """Raw output of an AI call — for auditing and cost tracking."""

    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), default=None, index=True
    )

    kind: Mapped[AnalysisKind] = mapped_column(String(30), index=True)
    model: Mapped[str] = mapped_column(String(100))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    latency_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    # The AI may refuse (stop_reason="refusal"); we record it to fall back to manual.
    was_refusal: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    cost_usd: Mapped[float | None] = mapped_column(Float, default=None)

    job: Mapped[Job | None] = relationship(back_populates="analyses")


class TailoredResume(Base, TimestampMixin):
    """A resume adapted to one job — reorganized and re-emphasized, never invented.

    One per (user, job): re-tailoring the same job overwrites the draft. `content`
    starts as the model's output and becomes the user's once they edit it.
    `invention_flags` holds the invention-guard's output — technologies present in
    the tailored text but absent from the source — for the user to verify.
    """

    __tablename__ = "tailored_resumes"
    __table_args__ = (UniqueConstraint("job_id", name="uq_tailored_resume_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, index=True
    )

    content: Mapped[str] = mapped_column(Text, default="")
    # [{"section", "action", "detail"}] — the edits the model reported making.
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    unsupported_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    invention_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # [{"text", "why_stretch"}] — grounded but aggressive claims the user should
    # keep, soften, or drop; the middle band the binary invention guard lacks.
    stretch_flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    # Hash of the source resume when this was generated, to detect a stale draft
    # after the user edits their profile.
    source_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    was_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    job: Mapped[Job] = relationship(back_populates="tailored_resume")
