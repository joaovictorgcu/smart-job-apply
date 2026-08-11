"""Candidaturas e sua trilha de eventos."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.ai.schemas import ScreeningAnswer
from app.models.enums import ApplicationEventType, ApplicationStatus
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
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    """Edições do usuário na revisão, antes de aprovar o envio."""

    cover_letter: str | None = None
    screening_answers: list[ScreeningAnswer] | None = None
