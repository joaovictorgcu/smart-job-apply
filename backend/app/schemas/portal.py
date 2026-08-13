"""External job-portal discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PortalSearchRequest(BaseModel):
    portal: str = Field(max_length=30, description="Registry key, e.g. 'gupy'.")
    keywords: str = Field(min_length=1, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=25, ge=1, le=50)


class PortalSearchResult(BaseModel):
    portal: str
    jobs_found: int
    jobs_new: int
