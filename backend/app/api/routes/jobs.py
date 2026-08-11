"""Discovered jobs, their scores and their triage actions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, LimitDep, OffsetDep, SessionDep
from app.models import JobStatus
from app.schemas.common import Page
from app.schemas.job import JobDetail, JobRead
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=Page[JobRead])
async def list_jobs(
    user: CurrentUser,
    session: SessionDep,
    status: Annotated[JobStatus | None, Query(description="Filter by lifecycle status.")] = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    search_id: Annotated[int | None, Query(description="Only jobs from this saved search.")] = None,
    limit: LimitDep = 50,
    offset: OffsetDep = 0,
) -> Page[JobRead]:
    """List jobs, best score first. Each item carries the id of its application, if any."""
    jobs, total = await job_service.list_jobs(
        session,
        user,
        status=status,
        min_score=min_score,
        search_id=search_id,
        limit=limit,
        offset=offset,
    )
    return Page[JobRead](
        items=[job_service.to_job_read(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobDetail)
async def read_job(job_id: int, user: CurrentUser, session: SessionDep) -> JobDetail:
    """Return one job including its full description."""
    job = await job_service.get_job(session, user, job_id)
    return job_service.to_job_detail(job)


@router.post("/{job_id}/skip", response_model=JobRead)
async def skip_job(job_id: int, user: CurrentUser, session: SessionDep) -> JobRead:
    """Take a job out of the queue. Reversible only by re-running the search."""
    job = await job_service.skip_job(session, user, job_id)
    return job_service.to_job_read(job)


@router.post("/{job_id}/analyze", response_model=JobRead)
async def analyze_job(job_id: int, user: CurrentUser, session: SessionDep) -> JobRead:
    """Score this job against the profile with the AI.

    Scoring only reads: it never opens the application form and never submits.
    Requires the job description, which the search step collects.
    """
    job = await job_service.analyze_job(session, user, job_id)
    return job_service.to_job_read(job)
