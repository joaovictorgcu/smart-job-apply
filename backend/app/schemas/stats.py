"""Dashboard metrics."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreBucket(BaseModel):
    label: str  # e.g. "80-100"
    count: int


class DailyCount(BaseModel):
    date: str  # ISO (YYYY-MM-DD)
    count: int


class OutcomeCount(BaseModel):
    outcome: str  # applied | interview | offer | rejected | ghosted
    count: int
    avg_score: float | None = None


class ScoreBandRate(BaseModel):
    """How often submitted applications in one score band reached an interview."""

    label: str  # e.g. "90-100"
    total: int
    interviews: int  # outcome in {interview, offer}
    rate: float | None = None  # interviews / total, or null when total is 0


class OutcomeStats(BaseModel):
    """Does a high AI match score actually lead to interviews?"""

    total_submitted: int = 0
    interviews: int = 0  # outcome in {interview, offer}
    offers: int = 0
    rejected: int = 0
    ghosted: int = 0
    interview_rate: float | None = None
    by_outcome: list[OutcomeCount] = Field(default_factory=list)
    interview_rate_by_band: list[ScoreBandRate] = Field(default_factory=list)


class DashboardStats(BaseModel):
    jobs_total: int = 0
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    applications_total: int = 0
    applications_today: int = 0
    awaiting_review: int = 0
    daily_cap: int = 0
    remaining_today: int = 0
    average_score: float | None = None
    score_distribution: list[ScoreBucket] = Field(default_factory=list)
    applications_last_7_days: list[DailyCount] = Field(default_factory=list)
    ai_calls_total: int = 0
    ai_tokens_input: int = 0
    ai_tokens_output: int = 0
