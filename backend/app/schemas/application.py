"""Applications and their event trail."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.ai.schemas import ScreeningAnswer
from app.models.enums import ApplicationEventType, ApplicationOutcome, ApplicationStatus
from app.schemas.common import ORMModel
from app.schemas.job import JobRead


class ApplicationRead(ORMModel):
    id: int
    job_id: int
    status: ApplicationStatus
    cover_letter: str | None = None
    screening_answers: list[dict[str, Any]] = Field(default_factory=list)
    resume_filename: str | None = None
    total_steps: int | None = None
    current_step: int | None = None
    needs_human_input: bool = False
    was_dry_run: bool = False
    approved_at: datetime | None = None
    submitted_at: datetime | None = None
    error_message: str | None = None
    outcome: ApplicationOutcome | None = None
    outcome_updated_at: datetime | None = None
    outcome_note: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplicationCard(BaseModel):
    """A submitted application as it appears on the pipeline board."""

    id: int
    job_id: int
    title: str
    company: str
    location: str | None = None
    score: int | None = None
    outcome: ApplicationOutcome
    submitted_at: datetime | None = None
    outcome_updated_at: datetime | None = None


class OutcomeUpdate(BaseModel):
    """Move a submitted application to a new real-world outcome."""

    outcome: ApplicationOutcome
    note: str | None = Field(default=None, max_length=500)


class ApplicationEventOut(ORMModel):
    id: int
    event_type: ApplicationEventType
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    is_error: bool = False
    created_at: datetime


class ApplicationDetail(ApplicationRead):
    job: JobRead | None = None
    events: list[ApplicationEventOut] = Field(default_factory=list)


class ApplicationUpdate(BaseModel):
    """The user's edits during review, before approving the submission."""

    cover_letter: str | None = None
    screening_answers: list[ScreeningAnswer] | None = None
