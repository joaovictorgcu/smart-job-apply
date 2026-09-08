"""User, profile, settings and LinkedIn connection status."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.common import ORMModel


class UserRead(ORMModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class ResumeHighlight(BaseModel):
    """One achievement of one experience, tagged with what it is about.

    `technologies` is not decoration: it is how a derivation picks which of the
    user's own bullets lead for a given posting, so a .NET vacancy and a React
    vacancy honestly show different sentences from the same job. Untagged
    bullets still work — they are matched on their text alone.
    """

    text: str = Field(min_length=1, max_length=1000)
    technologies: list[str] = Field(default_factory=list, max_length=40)


class ResumeExperienceIn(BaseModel):
    """One position of the master resume."""

    # Stable across edits so a derived version can point back at its source
    # entry. Generated when absent, never required from the client.
    id: str | None = Field(default=None, max_length=80)
    role: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    start: str = Field(default="", max_length=40)
    end: str = Field(default="", max_length=40)
    location: str = Field(default="", max_length=200)
    # The neutral description, used for a posting that matches no highlight.
    summary: str = Field(default="", max_length=2000)
    highlights: list[ResumeHighlight] = Field(default_factory=list, max_length=30)
    technologies: list[str] = Field(default_factory=list, max_length=60)


class ResumeProjectIn(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    outcome: str = Field(default="", max_length=500)
    technologies: list[str] = Field(default_factory=list, max_length=60)


class ResumeEducationIn(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    degree: str = Field(default="", max_length=200)
    institution: str = Field(default="", max_length=200)
    start: str = Field(default="", max_length=40)
    end: str = Field(default="", max_length=40)
    detail: str = Field(default="", max_length=1000)


class ProfileRead(ORMModel):
    headline: str | None = None
    location: str | None = None
    phone: str | None = None
    years_of_experience: int | None = None
    summary: str | None = None
    resume_text: str | None = None
    resume_filename: str | None = None
    skills: list[str] = Field(default_factory=list)
    # The structured master resume. Read back as loose JSON rather than through
    # the `*In` models: rows written before this existed, or by an earlier shape
    # of it, must still render instead of failing validation on the way out.
    experiences: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    answer_bank: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None


class ProfileUpdate(BaseModel):
    headline: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    years_of_experience: int | None = Field(default=None, ge=0, le=70)
    summary: str | None = None
    resume_text: str | None = None
    skills: list[str] | None = None
    # Validated on the way in — this is the document every future application
    # derives from, and a malformed entry here would quietly degrade every one
    # of them. Omitted fields are left untouched, as everywhere else here.
    experiences: list[ResumeExperienceIn] | None = Field(default=None, max_length=40)
    projects: list[ResumeProjectIn] | None = Field(default=None, max_length=40)
    education: list[ResumeEducationIn] | None = Field(default=None, max_length=20)
    certifications: list[str] | None = Field(default=None, max_length=40)
    preferred_languages: list[str] | None = None
    answer_bank: dict[str, Any] | None = None


class UserSettingsRead(ORMModel):
    daily_cap: int
    min_score: int
    action_delay_min: float
    action_delay_max: float
    apply_delay_min: float
    apply_delay_max: float
    working_hour_start: int
    working_hour_end: int
    require_manual_approval: bool
    dry_run: bool
    ai_model: str | None = None
    cover_letter_tone: str
    content_language: str
    generate_cover_letter: bool


class UserSettingsUpdate(BaseModel):
    # Cap of 50/day: above that the usage pattern stops looking human.
    daily_cap: int | None = Field(default=None, ge=1, le=50)
    min_score: int | None = Field(default=None, ge=0, le=100)
    action_delay_min: float | None = Field(default=None, ge=0.5, le=60)
    action_delay_max: float | None = Field(default=None, ge=0.5, le=120)
    apply_delay_min: float | None = Field(default=None, ge=5, le=600)
    apply_delay_max: float | None = Field(default=None, ge=5, le=1800)
    working_hour_start: int | None = Field(default=None, ge=0, le=23)
    working_hour_end: int | None = Field(default=None, ge=1, le=24)
    require_manual_approval: bool | None = None
    dry_run: bool | None = None
    ai_model: str | None = Field(default=None, max_length=100)
    cover_letter_tone: str | None = Field(default=None, max_length=50)
    content_language: str | None = Field(default=None, max_length=20)
    generate_cover_letter: bool | None = None

    @model_validator(mode="after")
    def _check_ranges(self) -> UserSettingsUpdate:
        if (
            self.action_delay_min is not None
            and self.action_delay_max is not None
            and self.action_delay_min > self.action_delay_max
        ):
            raise ValueError("action_delay_min cannot be greater than action_delay_max.")
        if (
            self.apply_delay_min is not None
            and self.apply_delay_max is not None
            and self.apply_delay_min > self.apply_delay_max
        ):
            raise ValueError("apply_delay_min cannot be greater than apply_delay_max.")
        if (
            self.working_hour_start is not None
            and self.working_hour_end is not None
            and self.working_hour_start >= self.working_hour_end
        ):
            raise ValueError("working_hour_start must be less than working_hour_end.")
        return self


class AuditEventRead(ORMModel):
    """One recorded account change.

    `relaxed` is what the trail exists for: which guardrails were loosened, and
    therefore which entries deserve a second look.
    """

    id: int
    action: str
    subject_type: str
    subject_id: int | None = None
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    relaxed: list[str] = Field(default_factory=list)
    created_at: datetime


class LinkedInAccountRead(ORMModel):
    """Metadata only. No cookie or credential ever leaves through the API."""

    display_name: str | None = None
    is_connected: bool = False
    last_verified_at: datetime | None = None


class SessionStatus(BaseModel):
    """Current browser/automation state, for the dashboard."""

    browser_open: bool = False
    logged_in: bool = False
    blocked: bool = False
    blocked_reason: str | None = None
    active_run_id: int | None = None
    applications_today: int = 0
    daily_cap: int = 0
    dry_run: bool = True
    ai_configured: bool = False
