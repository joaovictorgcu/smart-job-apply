"""Application user, professional profile and settings."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.automation import AutomationRun
    from app.models.job import Application, Job, Search


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
    linkedin_account: Mapped[LinkedInAccount | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
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
    cover_letter_tone: Mapped[str] = mapped_column(String(50), default="profissional")
    # "job" = follow the job posting's language; or pin "pt-BR" / "en".
    content_language: Mapped[str] = mapped_column(String(20), default="job")
    generate_cover_letter: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="settings")


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
