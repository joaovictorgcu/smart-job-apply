"""Searches and jobs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

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
    skip_reason: str | None = None
    detected_language: str | None = None
    posted_at: datetime | None = None
    created_at: datetime | None = None
    search_id: int | None = None
    application_id: int | None = None


class JobDetail(JobRead):
    description: str | None = None
