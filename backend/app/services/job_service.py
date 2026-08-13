"""Jobs: listing, deduplicated ingestion, status transitions and AI scoring."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.schemas import CoverLetter
from app.api.errors import NotFoundError, PreconditionFailedError, UpstreamError
from app.automation.contracts import JobPosting
from app.models import Job, JobStatus, User
from app.observability import EventName, get_logger, make_event
from app.schemas.job import JobDetail, JobRead
from app.services import user_service
from app.websocket.manager import manager

logger = get_logger(__name__)


def _job_query() -> Select[tuple[Job]]:
    # `JobRead.application_id` has no backing column, so the relationship is always
    # eagerly loaded and the id is filled in explicitly by `to_job_read`.
    return select(Job).options(selectinload(Job.application))


async def list_jobs(
    session: AsyncSession,
    user: User,
    *,
    status: JobStatus | None = None,
    min_score: int | None = None,
    search_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    """Return one page of the user's jobs plus the total matching count."""
    conditions = [Job.user_id == user.id]
    if status is not None:
        conditions.append(Job.status == status)
    if min_score is not None:
        conditions.append(Job.score >= min_score)
    if search_id is not None:
        conditions.append(Job.search_id == search_id)

    total_result = await session.execute(select(func.count()).select_from(Job).where(*conditions))
    total = int(total_result.scalar_one())

    result = await session.execute(
        _job_query()
        .where(*conditions)
        .order_by(Job.score.desc().nullslast(), Job.created_at.desc(), Job.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def get_job(session: AsyncSession, user: User, job_id: int) -> Job:
    result = await session.execute(_job_query().where(Job.id == job_id, Job.user_id == user.id))
    job = result.scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found.")
    return job


async def get_jobs_by_ids(session: AsyncSession, user: User, job_ids: list[int]) -> list[Job]:
    """Load the subset of `job_ids` that actually belongs to this user."""
    if not job_ids:
        return []
    result = await session.execute(_job_query().where(Job.user_id == user.id, Job.id.in_(job_ids)))
    return list(result.scalars().all())


async def upsert_job_from_posting(
    session: AsyncSession,
    user: User,
    posting: JobPosting,
    *,
    search_id: int | None = None,
) -> tuple[Job, bool]:
    """Insert or refresh a job, deduplicating on `(user_id, external_id)`.

    Returns `(job, created)`. An already-applied job is never pushed back to an
    earlier state, so re-running a search cannot resurrect finished work.
    """
    result = await session.execute(
        _job_query().where(Job.user_id == user.id, Job.external_id == posting.external_id)
    )
    job = result.scalar_one_or_none()
    created = job is None

    if job is None:
        job = Job(
            user_id=user.id,
            external_id=posting.external_id,
            title=posting.title,
            company=posting.company,
            status=JobStatus.DISCOVERED,
        )
        session.add(job)

    job.title = posting.title or job.title
    job.company = posting.company or job.company
    job.location = posting.location or job.location
    job.url = posting.url or job.url
    if posting.description:
        job.description = posting.description
    job.workplace_type = posting.workplace_type or job.workplace_type
    job.easy_apply = posting.easy_apply or job.easy_apply
    job.posted_at = posting.posted_at or job.posted_at
    if search_id is not None:
        job.search_id = search_id
    if posting.already_applied and job.status != JobStatus.APPLIED:
        job.status = JobStatus.APPLIED

    await session.flush()
    return job, created


async def skip_job(
    session: AsyncSession, user: User, job_id: int, *, reason: str | None = None
) -> Job:
    job = await get_job(session, user, job_id)
    if job.status == JobStatus.APPLIED:
        raise PreconditionFailedError("This job was already applied to and cannot be skipped.")
    job.status = JobStatus.SKIPPED
    job.skip_reason = reason or "Skipped by the user."
    await session.flush()
    logger.info(
        "Job skipped.",
        extra={"action": "job.skip", "status": "ok", "user_id": user.id, "job_id": job.id},
    )
    return job


async def mark_status(
    session: AsyncSession,
    user: User,
    job_id: int,
    status: JobStatus,
    *,
    skip_reason: str | None = None,
) -> Job:
    job = await get_job(session, user, job_id)
    job.status = status
    if skip_reason is not None:
        job.skip_reason = skip_reason
    await session.flush()
    return job


async def count_by_status(session: AsyncSession, user: User) -> dict[str, int]:
    result = await session.execute(
        select(Job.status, func.count()).where(Job.user_id == user.id).group_by(Job.status)
    )
    counts = {str(status): 0 for status in JobStatus}
    for status, count in result.all():
        counts[str(status)] = int(count)
    return counts


async def _require_described_job(session: AsyncSession, user: User, job_id: int) -> Job:
    job = await get_job(session, user, job_id)
    if not job.description:
        raise PreconditionFailedError(
            "This job has no description yet. Run a search with analysis enabled first."
        )
    return job


async def analyze_job(session: AsyncSession, user: User, job_id: int) -> Job:
    """Score one job against the profile with the AI.

    The AI layer owns the scoring transaction: it appends the `AIAnalysis` audit
    row and updates the job's score and status (including dropping it to `SKIPPED`
    when the score is below the user's minimum). This function only supplies the
    context and reports the outcome.
    """
    from app.ai import analyze_job as ai_analyze_job

    job = await _require_described_job(session, user, job_id)
    profile = await user_service.build_profile_context(session, user)
    user_settings = await user_service.get_or_create_settings(session, user)

    analysis = await ai_analyze_job(
        session, user=user, job=job, profile_ctx=profile, settings_row=user_settings
    )
    await session.flush()

    if analysis.refused:
        await manager.publish(
            user.id,
            make_event(
                EventName.JOB_ANALYZED,
                job_id=job.id,
                message=f"Could not score {job.title}: {analysis.refusal_reason}",
                level="warning",
                data={"refused": True},
            ),
        )
        logger.warning(
            "Job scoring produced no score.",
            extra={
                "action": "job.analyze",
                "status": "refused",
                "user_id": user.id,
                "job_id": job.id,
            },
        )
        return job

    await manager.publish(
        user.id,
        make_event(
            EventName.JOB_ANALYZED,
            job_id=job.id,
            message=f"{job.title} at {job.company} scored {analysis.score}.",
            level="success" if analysis.score >= user_settings.min_score else "info",
            data={"score": analysis.score, "recommend_apply": analysis.recommend_apply},
        ),
    )
    logger.info(
        "Job analyzed.",
        extra={
            "action": "job.analyze",
            "status": "ok",
            "user_id": user.id,
            "job_id": job.id,
            "score": analysis.score,
        },
    )
    return job


async def generate_cover_letter(session: AsyncSession, user: User, job_id: int) -> CoverLetter:
    """Draft a cover letter for one job.

    The AI layer records the call for cost auditing. The text is returned for the
    user to review: attaching it to a draft is a separate, explicit edit.
    """
    from app.ai import generate_cover_letter as ai_generate_cover_letter

    job = await _require_described_job(session, user, job_id)
    user_settings = await user_service.get_or_create_settings(session, user)
    if not user_settings.generate_cover_letter:
        raise PreconditionFailedError(
            "Cover letter generation is disabled in settings. Enable it and try again."
        )
    profile = await user_service.build_profile_context(session, user)

    letter = await ai_generate_cover_letter(
        session, user=user, job=job, profile_ctx=profile, settings_row=user_settings
    )
    await session.flush()
    if letter is None:
        raise UpstreamError("The AI did not return a cover letter. Try again, or write it by hand.")

    logger.info(
        "Cover letter generated.",
        extra={
            "action": "ai.cover_letter",
            "status": "ok",
            "user_id": user.id,
            "job_id": job.id,
            "language": letter.language,
        },
    )
    return letter


def to_posting(job: Job) -> JobPosting:
    """Convert a stored job back into the automation layer's contract."""
    return JobPosting(
        external_id=job.external_id,
        title=job.title,
        company=job.company,
        location=job.location,
        url=job.url,
        description=job.description,
        workplace_type=job.workplace_type,
        easy_apply=job.easy_apply,
        posted_at=job.posted_at,
        already_applied=job.status == JobStatus.APPLIED,
    )


def to_job_read(job: Job) -> JobRead:
    """Build the response model, filling the `application_id` the ORM cannot map."""
    return JobRead(
        id=job.id,
        external_id=job.external_id,
        source=job.source or "linkedin",
        title=job.title,
        company=job.company,
        location=job.location,
        url=job.url,
        workplace_type=job.workplace_type,
        easy_apply=job.easy_apply,
        status=job.status,
        score=job.score,
        score_reasons=list(job.score_reasons or []),
        missing_requirements=list(job.missing_requirements or []),
        score_breakdown=list(job.score_breakdown or []),
        score_gates=list(job.score_gates or []),
        skip_reason=job.skip_reason,
        detected_language=job.detected_language,
        posted_at=job.posted_at,
        created_at=job.created_at,
        search_id=job.search_id,
        application_id=job.application.id if job.application else None,
    )


def to_job_detail(job: Job) -> JobDetail:
    return JobDetail(**to_job_read(job).model_dump(), description=job.description)
