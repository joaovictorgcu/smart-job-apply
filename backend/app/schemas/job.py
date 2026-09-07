"""Searches and jobs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.ai.schemas import ScoreDimension, ScoreGate
from app.models.enums import JobStatus
from app.schemas.common import ORMModel


class SearchBase(BaseModel):
    name: str = Field(max_length=200)
    keywords: str = Field(min_length=1, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    remote_filter: str | None = Field(default=None, max_length=50)
    experience_levels: list[str] = Field(default_factory=list)
    date_posted: str | None = Field(default=None, max_length=30)
    easy_apply_only: bool = True
    # Per-run cap — avoids long sweeps that draw attention.
    max_results: int = Field(default=25, ge=1, le=100)


class SearchCreate(SearchBase):
    pass


class SearchUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    keywords: str | None = Field(default=None, min_length=1, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    remote_filter: str | None = Field(default=None, max_length=50)
    experience_levels: list[str] | None = None
    date_posted: str | None = Field(default=None, max_length=30)
    easy_apply_only: bool | None = None
    max_results: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None


class SearchRead(ORMModel, SearchBase):
    id: int
    is_active: bool = True
    last_run_at: datetime | None = None
    created_at: datetime | None = None


class JobRead(ORMModel):
    id: int
    external_id: str
    source: str = "linkedin"
    title: str
    company: str
    location: str | None = None
    url: str | None = None
    workplace_type: str | None = None
    easy_apply: bool = False
    status: JobStatus
    score: int | None = None
    score_reasons: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    score_breakdown: list[ScoreDimension] = Field(default_factory=list)
    score_gates: list[ScoreGate] = Field(default_factory=list)
    # Derived on read from `score` and `score_breakdown`, never stored: a column
    # would need a migration and would then go stale the moment the bands or the
    # weighting changed. Jobs scored before the breakdown carried weights report
    # `None` for the two derived numbers instead of a fabricated one.
    verdict: str | None = Field(
        default=None, description="Band the score falls in (strong, good, moderate, weak, poor)."
    )
    weighted_score: int | None = Field(
        default=None, description="The score recomputed from the breakdown's own weights."
    )
    score_divergence: int | None = Field(
        default=None, description="Overall score minus the weighted one; surfaced, not applied."
    )
    skip_reason: str | None = None
    detected_language: str | None = None
    posted_at: datetime | None = None
    deadline: datetime | None = None
    expired_at: datetime | None = None
    # Derived, like `verdict`: the posting is gone or its deadline has passed, so
    # preparing it would spend a submission on a job that can no longer be applied
    # to. Computed on read because it changes with the clock, not with a write.
    is_stale: bool = Field(
        default=False, description="Expired, or past its deadline — refused by preparation."
    )
    created_at: datetime | None = None
    search_id: int | None = None
    application_id: int | None = None


class JobDetail(JobRead):
    description: str | None = None


class JobUpdate(BaseModel):
    """The only job field the user may edit directly.

    Everything else on a job is either the portal's word or the pipeline's, and
    letting a request overwrite a score or a status would make both meaningless.
    `deadline` is different: no adapter reports one today, so the user is the only
    source there is. Sending `null` clears it; omitting the key leaves it alone.
    """

    deadline: datetime | None = None


class JobScoreRead(ORMModel):
    """One verdict from the job's scoring history."""

    id: int
    job_id: int
    overall: int
    verdict: str
    dimensions: list[ScoreDimension] = Field(default_factory=list)
    gates: list[ScoreGate] = Field(default_factory=list)
    model: str
    depth: str
    profile_fingerprint: str | None = None
    created_at: datetime
