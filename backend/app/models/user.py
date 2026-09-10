"""Application user, professional profile and settings."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.audit import AuditEvent
    from app.models.automation import AutomationRun
    from app.models.job import Application, Job, Search
    from app.models.resume import Experience


class User(Base, TimestampMixin):
    """Local application account.

    We only keep credentials for **our own application** (a bcrypt hash). The
    LinkedIn password is never stored: the user logs in manually in the browser and
    the session is persisted as encrypted cookies (see `LinkedInAccount`).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(200), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    profile: Mapped[Profile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    preferences: Mapped[JobPreferences | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    linkedin_account: Mapped[LinkedInAccount | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    # The structured half of the master resume. `Profile` keeps the free text and
    # the answer bank; the positions live here because the per-application
    # derivation has to reason about them one at a time.
    experiences: Mapped[list[Experience]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Experience.position",
    )
    searches: Mapped[list[Search]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[list[Application]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    runs: Mapped[list[AutomationRun]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Profile(Base, TimestampMixin):
    """Resume as text plus the answer bank used by the AI."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    headline: Mapped[str | None] = mapped_column(String(300), default=None)
    location: Mapped[str | None] = mapped_column(String(200), default=None)
    phone: Mapped[str | None] = mapped_column(String(50), default=None)
    years_of_experience: Mapped[int | None] = mapped_column(Integer, default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    resume_text: Mapped[str | None] = mapped_column(Text, default=None)
    resume_filename: Mapped[str | None] = mapped_column(String(255), default=None)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_languages: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Default answers for recurring screening questions, e.g.:
    # {"salary_expectation": "15,000", "notice_period": "30 days",
    #  "work_authorization": "Yes", "years_python": "6"}
    answer_bank: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="profile")


class UserSettings(Base, TimestampMixin):
    """Per-user automation guardrails and AI preferences."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # --- Guardrails ---
    daily_cap: Mapped[int] = mapped_column(Integer, default=15)
    min_score: Mapped[int] = mapped_column(Integer, default=70)
    action_delay_min: Mapped[float] = mapped_column(default=2.5)
    action_delay_max: Mapped[float] = mapped_column(default=7.0)
    apply_delay_min: Mapped[float] = mapped_column(default=45.0)
    apply_delay_max: Mapped[float] = mapped_column(default=120.0)
    working_hour_start: Mapped[int] = mapped_column(Integer, default=8)
    working_hour_end: Mapped[int] = mapped_column(Integer, default=20)
    # No submission without explicit confirmation. Turning this off means
    # accepting the risk knowingly.
    require_manual_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)

    # --- AI ---
    ai_model: Mapped[str | None] = mapped_column(String(100), default=None)
    cover_letter_tone: Mapped[str] = mapped_column(String(50), default="professional")
    # "job" = follow the job posting's language; or pin "pt-BR" / "en".
    content_language: Mapped[str] = mapped_column(String(20), default="job")
    generate_cover_letter: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="settings")


class JobPreferences(Base, TimestampMixin):
    """What kind of vacancy this account is looking for.

    Separate from `Search`, and the distinction is the point. A `Search` is one
    reusable query against one portal, with that portal's own filter
    vocabulary. This is the standing answer to "what am I looking for" — the
    thing a user states once, in their own terms, that then feeds the query,
    the triage and the emphasis of every adapted resume.

    Kept apart from `Profile` because it is not identity: the profile says what
    the candidate *has done*, this says what they *want next*, and the two move
    independently. And apart from `UserSettings`, which is operational
    guardrails with safety implications; getting this wrong costs a bad
    recommendation, not an unwanted submission.

    Every list holds the user's own words. `excluded_terms` and
    `priority_technologies` in particular are matched, never generated from.
    """

    __tablename__ = "job_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # The one role that drives the query. Alternatives widen it without
    # diluting it: they are searched too, but never rank above the main one.
    target_role: Mapped[str | None] = mapped_column(String(200), default=None)
    alternative_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    # LinkedIn's own vocabulary, so this maps onto a search with no translation
    # table: internship / entry / associate / mid-senior / director / executive.
    seniority: Mapped[list[str]] = mapped_column(JSON, default=list)
    # remote / hybrid / on-site — same values `Search.remote_filter` accepts.
    work_models: Mapped[list[str]] = mapped_column(JSON, default=list)
    locations: Mapped[list[str]] = mapped_column(JSON, default=list)

    # A floor, not a range: "below this I am not interested" is the only part of
    # a salary expectation a posting can actually be screened against.
    salary_min: Mapped[int | None] = mapped_column(Integer, default=None)
    salary_currency: Mapped[str] = mapped_column(String(10), default="BRL")

    # Technologies to lead with when they appear in a posting. They can only
    # re-rank what the candidate already claims — a term here that is not in
    # their resume changes nothing, by construction.
    priority_technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Words that disqualify a posting outright, matched against its title,
    # location and workplace type. Deliberately not the description: "call
    # center" in a benefits paragraph is not a call-centre job.
    excluded_terms: Mapped[list[str]] = mapped_column(JSON, default=list)

    user: Mapped[User] = relationship(back_populates="preferences")


class LinkedInAccount(Base, TimestampMixin):
    """The user's LinkedIn session — **cookies encrypted at rest**.

    We never store the LinkedIn email/password. The user logs in manually in the
    browser; we persist only the session state, encrypted with Fernet (AES-CBC
    plus HMAC) via `app.auth.crypto`.
    """

    __tablename__ = "linkedin_accounts"
    __table_args__ = (UniqueConstraint("user_id", name="uq_linkedin_account_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    # Informational label only (e.g. the display name shown on LinkedIn).
    display_name: Mapped[str | None] = mapped_column(String(200), default=None)
    encrypted_storage_state: Mapped[str | None] = mapped_column(Text, default=None)
    browser_profile_dir: Mapped[str | None] = mapped_column(String(500), default=None)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="linkedin_account")
