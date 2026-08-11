"""Tailored-resume request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CVChangeOut(BaseModel):
    section: str
    action: str
    detail: str


class TailoredResumeRead(BaseModel):
    job_id: int
    content: str
    changes: list[CVChangeOut] = Field(default_factory=list)
    # Requirements the resume genuinely cannot back — surfaced, not invented.
    unsupported_requirements: list[str] = Field(default_factory=list)
    # Technologies the invention guard found in the tailored text but not the
    # source; the user verifies each one.
    invention_flags: list[str] = Field(default_factory=list)
    summary: str | None = None
    model: str | None = None
    was_edited: bool = False
    # True when the profile changed after this draft was generated.
    is_stale: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TailoredResumeUpdate(BaseModel):
    """The user's edits to the tailored resume before they use it."""

    content: str = Field(min_length=1)
