"""Automation runs: start a search, prepare, confirm submission."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AutomationRunKind, AutomationRunStatus
from app.schemas.common import ORMModel
from app.schemas.job import JobRead


class SearchRunRequest(BaseModel):
    """Runs a saved search or ad-hoc filters."""

    search_id: int | None = None
    keywords: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    remote_filter: str | None = None
    date_posted: str | None = None
    experience_levels: list[str] = Field(default_factory=list)
    max_results: int = Field(default=25, ge=1, le=100)
    # Search plus AI analysis never submits anything; submitting is always a separate step.
    analyze: bool = True


class PreviewResponse(BaseModel):
    """Confirmation before processing: the user sees the volume and decides.

    Required before any real application, so there is never a "I submitted dozens
    without you seeing them" surprise.
    """

    jobs_to_process: int
    already_applied: int = 0
    below_threshold: int = 0
    remaining_today: int = 0
    daily_cap: int = 0
    dry_run: bool = True
    requires_confirmation: bool = True
    jobs: list[JobRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PrepareRequest(BaseModel):
    """Fills the form up to the review step. Does not submit."""

    job_ids: list[int] = Field(min_length=1, max_length=50)
    confirmed: bool = Field(
        default=False, description="Must be true once the user has reviewed the preview."
    )


class SubmitRequest(BaseModel):
    """Explicit approval of an application that has already been reviewed."""

    confirm: bool = Field(description="Must be true; this is the consent to submit.")


class AutomationRunRead(ORMModel):
    id: int
    kind: AutomationRunKind
    status: AutomationRunStatus
    dry_run: bool
    search_id: int | None = None
    jobs_found: int = 0
    jobs_analyzed: int = 0
    jobs_skipped: int = 0
    applications_prepared: int = 0
    applications_submitted: int = 0
    stop_requested: bool = False
    blocked_reason: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
