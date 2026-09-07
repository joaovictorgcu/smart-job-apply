"""Per-application resume request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.schemas import StretchFlag


class CVChangeOut(BaseModel):
    section: str
    action: str
    detail: str


# Every field below is read back out of a JSON column, so every model here is
# permissive: `extra="ignore"` and a default on everything. A version derived by
# an earlier shape of the engine must still render rather than 500 on the way
# out, and a version derived before the structure existed has no sections at all.
class _StoredModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TailoredExperienceOut(_StoredModel):
    """One experience as this application presents it."""

    id: str = ""
    role: str = ""
    company: str = ""
    period: str = ""
    location: str = ""
    # Composed from the user's own highlights — this is the adapted description.
    description: str = ""
    highlights: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    # Which of the posting's keywords this entry backs.
    matched: list[str] = Field(default_factory=list)
    # 0-100, relative to the strongest entry in this version.
    relevance: int = 0
    emphasis: Literal["lead", "support", "context"] = "context"
    # Bullets from the master resume this version left out, so the user can see
    # what was set aside rather than wondering where it went.
    omitted: list[str] = Field(default_factory=list)


class TailoredProjectOut(_StoredModel):
    id: str = ""
    name: str = ""
    description: str = ""
    outcome: str = ""
    technologies: list[str] = Field(default_factory=list)
    matched: list[str] = Field(default_factory=list)
    relevance: int = 0


class ResumeEducationOut(_StoredModel):
    id: str = ""
    degree: str = ""
    institution: str = ""
    start: str = ""
    end: str = ""
    detail: str = ""


class ResumeSectionsOut(_StoredModel):
    """The structured, per-application resume the review screen renders.

    Identity is verbatim from the master; only ordering, selection and emphasis
    are derived. That distinction is what the screen is built to show.
    """

    full_name: str = ""
    headline: str = ""
    location: str = ""
    summary: str = ""
    years_of_experience: int | None = None
    prioritized_skills: list[str] = Field(default_factory=list)
    other_skills: list[str] = Field(default_factory=list)
    experiences: list[TailoredExperienceOut] = Field(default_factory=list)
    projects: list[TailoredProjectOut] = Field(default_factory=list)
    education: list[ResumeEducationOut] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    language: str = "pt"


class ResumeFocusOut(_StoredModel):
    """The posting reduced to what was matched — why this version looks like this."""

    title: str = ""
    company: str = ""
    level: str | None = None
    keywords: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)


class TailoredResumeRead(BaseModel):
    job_id: int
    content: str
    changes: list[CVChangeOut] = Field(default_factory=list)
    # Requirements the resume genuinely cannot back — surfaced, not invented.
    unsupported_requirements: list[str] = Field(default_factory=list)
    # Technologies the invention guard found in the tailored text but not the
    # source; the user verifies each one.
    invention_flags: list[str] = Field(default_factory=list)
    # Grounded but aggressive claims — keep, soften, or drop is the user's call.
    stretch_flags: list[StretchFlag] = Field(default_factory=list)
    summary: str | None = None
    model: str | None = None
    was_edited: bool = False
    # True when the profile changed after this version was derived.
    is_stale: bool = False
    # How `content` was written: the domain engine, or a model over the same
    # structure. Rows that predate the field report "ai", which is what they were.
    strategy: Literal["deterministic", "ai"] = "ai"
    # Null for a version derived before the structure existed. The screen falls
    # back to rendering `content` alone, which is what it always did.
    sections: ResumeSectionsOut | None = None
    focus: ResumeFocusOut | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplicationResumeRead(TailoredResumeRead):
    """The same version, addressed as one application's own.

    The job title and company travel with it so the screen can name the vacancy
    this version was built for — the first thing a user with five open
    applications needs to see.
    """

    application_id: int
    job_title: str | None = None
    job_company: str | None = None


class TailoredResumeUpdate(BaseModel):
    """The user's edits to this application's resume before they use it."""

    content: str = Field(min_length=1)


class ResumeDeriveRequest(BaseModel):
    """How to build this application's version.

    `deterministic` (the default) renders the derivation itself, so the document
    and the breakdown shown beside it always describe each other. `ai` asks a
    model to rewrite the prose over the same derivation, and is refused with 412
    when no API key is configured rather than silently falling back.
    """

    strategy: Literal["deterministic", "ai"] = "deterministic"
