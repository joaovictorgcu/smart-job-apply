"""The master resume's structured experience, and one adapted copy per application.

Two tables, and the split between them is the whole feature:

`Experience` is the candidate's own history, edited once on the profile page. It
is the *only* place a fact about the candidate lives.

`ApplicationResume` is what one application actually presents. It is a **full
snapshot**, not a view: every string it renders is stored on the row itself, and
`experience_id` is kept for provenance only — nothing ever dereferences it to
build the document. That is what makes the isolation rule structural rather than
a convention somebody has to remember:

    editing the master cannot reach an existing application's copy,
    and editing one application's copy cannot reach the master or a sibling.

The same reasoning already governs `Application.submitted_snapshot`: once a
document has been shown to a human as "this is what goes out", later edits
elsewhere must not rewrite it underneath them.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.job import Application, Job
    from app.models.user import User


class Experience(Base, TimestampMixin):
    """One position on the candidate's master resume.

    Structured rather than free text because the adaptation has to reason about
    the parts separately: a posting asking for PostgreSQL should promote the
    bullet that mentions it, which is impossible if the whole job is one blob.

    `responsibilities`, `technologies`, `results` are lists of the candidate's
    own sentences/terms. `projects` is
    `[{"name", "description", "technologies": [...]}]`. Nothing generated ever
    writes here — this table is the source of truth, and the adaptation only
    ever reads it.
    """

    __tablename__ = "experiences"
    __table_args__ = (Index("ix_experience_user_position", "user_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    company: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    # "full_time", "contract", "internship"... free text on purpose: the value is
    # rendered, never branched on.
    employment_type: Mapped[str | None] = mapped_column(String(50), default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)

    started_on: Mapped[date | None] = mapped_column(Date, default=None)
    ended_on: Mapped[date | None] = mapped_column(Date, default=None)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    summary: Mapped[str | None] = mapped_column(Text, default=None)
    responsibilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    results: Mapped[list[str]] = mapped_column(JSON, default=list)
    projects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    # Display order on the master resume. Ties break on `started_on`, so a user
    # who never reorders anything still gets a sensible reverse-chronological list.
    position: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="experiences")


class ApplicationResume(Base, TimestampMixin):
    """The resume one application presents — derived from the master, then frozen.

    One row per application (enforced by a unique constraint), so several
    applications by the same user hold several independent documents. Re-adapting
    replaces this row's content and bumps `version`; the *other* applications'
    rows are never touched, which is the isolation the feature promises.

    `experiences` is the adapted snapshot:
    `[{"experience_id", "company", "role", "period", "location", "summary",
       "focus", "responsibilities", "technologies", "results", "projects",
       "relevance", "matched_terms", "omitted_count"}]`

    `changes` is the report the review screen renders — what was prioritised,
    highlighted, emphasised or refocused, and why — as
    `[{"kind", "target", "detail"}]`.

    `fit_factors` is the adherence breakdown,
    `[{"factor", "score", "weight_pct", "detail"}]`, so "87%" can be argued with
    instead of taken on faith. Same principle as `Job.score_breakdown`.
    """

    __tablename__ = "application_resumes"
    __table_args__ = (UniqueConstraint("application_id", name="uq_application_resume_application"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), unique=True, index=True
    )
    # Denormalised from the application so the version list can name its posting
    # in one query. The application is the owner; this is a convenience.
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)

    # Bumped by "adapt again", so the user can tell a fresh derivation from the
    # one they have been editing. Deliberately not a separate history table: the
    # history that matters across applications is the sibling rows themselves.
    version: Mapped[int] = mapped_column(Integer, default=1)

    headline: Mapped[str | None] = mapped_column(String(300), default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    highlighted_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    emphasized_technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    experiences: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    projects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    fit_score: Mapped[int] = mapped_column(Integer, default=0)
    # No prose summary column beside these: the sentence explaining the number is
    # composed in the frontend from the factors, so a stored one would be a second
    # wording to keep in step with the first.
    fit_factors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Requirements the posting names that the master resume cannot back. Surfaced,
    # never written into the document — the same honesty valve as
    # `TailoredResume.unsupported_requirements`.
    uncovered_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Hash of the master resume this was derived from. A later master edit makes
    # the snapshot *stale*, never wrong: the user decides whether to re-adapt.
    source_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    # Null means the derivation was deterministic (no model call), which is the
    # only producer today. Kept so an AI-assisted pass can be attributed later.
    model: Mapped[str | None] = mapped_column(String(100), default=None)
    was_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    adapted_at: Mapped[datetime | None] = mapped_column(default=None)

    application: Mapped[Application] = relationship(back_populates="resume")
    job: Mapped[Job] = relationship()
