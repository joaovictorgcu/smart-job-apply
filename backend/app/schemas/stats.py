"""Dashboard metrics."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreBucket(BaseModel):
    label: str  # e.g. "80-100"
    count: int


class DailyCount(BaseModel):
    date: str  # ISO (YYYY-MM-DD)
    count: int


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
