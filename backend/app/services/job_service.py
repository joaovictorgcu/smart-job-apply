"""Jobs: listing, deduplicated ingestion, status transitions and AI scoring."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.schemas import CoverLetter, ScoreDimension
from app.api.errors import NotFoundError, PreconditionFailedError, UpstreamError
from app.automation.contracts import JobPosting
from app.database.base import utcnow
from app.domain import recommendation
from app.domain.language import detect_language
from app.domain.preferences import PreferenceVerdict, screen
from app.domain.scoring import verdict_for, weighted_score
from app.models import Job, JobScore, JobStatus, User
from app.observability import EventName, get_logger, make_event
from app.schemas.job import JobDetail, JobRead, JobScoreRead, JobUpdate, RecommendationRead
from app.services import preference_service, resume_service, user_service
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
    user_id: int,
    posting: JobPosting,
    *,
    search_id: int | None = None,
) -> tuple[Job, bool]:
    """Insert or refresh a job, deduplicating on `(user_id, external_id)`.

    The single ingestion rule for every discovery path — the API and the
    automation engine both come through here, so a posting is refreshed the same
    way whoever found it. Takes a `user_id` because the engine works from ids and
    holds no `User` row.

    Returns `(job, created)`. An already-applied job is never pushed back to an
    earlier state, so re-running a search cannot resurrect finished work.
    """
    result = await session.execute(
        _job_query().where(Job.user_id == user_id, Job.external_id == posting.external_id)
    )
    job = result.scalar_one_or_none()
    created = job is None

    if job is None:
        job = Job(
            user_id=user_id,
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
        job.detected_language = detect_language(posting.description)
    job.workplace_type = posting.workplace_type or job.workplace_type
    job.easy_apply = posting.easy_apply or job.easy_apply
    job.posted_at = posting.posted_at or job.posted_at
    # Credit the search that first found the posting; a later run that happens to
    # return it again must not re-attribute it.
    if search_id is not None and job.search_id is None:
        job.search_id = search_id
    if posting.already_applied and job.status != JobStatus.APPLIED:
        job.status = JobStatus.APPLIED
        job.skip_reason = "LinkedIn reports this application was already sent."

    await session.flush()
    return job, created


def stale_reason(job: Job, *, now: datetime | None = None) -> str | None:
    """Why this posting can no longer be applied to, or None if it still can.

    Two ways a posting dies: discovery found it gone (`expired_at`), or its own
    published deadline has passed. Both are computed against the clock rather than
    stored as a status, so a job does not need a sweep to become correct.
    """
    if job.expired_at is not None:
        return "This posting is no longer published."
    deadline = job.deadline
    if deadline is not None and deadline <= (now or utcnow()):
        return f"Applications closed on {deadline.date().isoformat()}."
    return None


def is_stale(job: Job, *, now: datetime | None = None) -> bool:
    """Whether preparation must refuse this job. See `stale_reason` for why."""
    return stale_reason(job, now=now) is not None


async def update_job(session: AsyncSession, user: User, job_id: int, payload: JobUpdate) -> Job:
    """Apply the user's edits. Only `deadline` is editable — see `JobUpdate`."""
    job = await get_job(session, user, job_id)
    if "deadline" in payload.model_fields_set:
        # Explicit `null` clears the deadline; an absent key is not an edit at all,
        # which a plain `payload.deadline` read could not tell apart.
        job.deadline = payload.deadline
    await session.flush()
    logger.info(
        "Job updated.",
        extra={
            "action": "job.update",
            "status": "ok",
            "user_id": user.id,
            "job_id": job.id,
            "has_deadline": job.deadline is not None,
        },
    )
    return job


async def expire_missing(
    session: AsyncSession, user: User, job_id: int, *, reason: str | None = None
) -> Job:
    """Record that discovery could not find this posting any more.

    Idempotent: the first sighting of the absence is the one that counts, so a
    second sweep does not push the timestamp forward. An already-applied job is
    stamped but never re-statused — postings routinely vanish after a successful
    application, and rewriting that history would lose the application.
    """
    job = await get_job(session, user, job_id)
    if job.expired_at is not None:
        return job

    job.expired_at = utcnow()
    if job.status != JobStatus.APPLIED:
        job.status = JobStatus.SKIPPED
        job.skip_reason = reason or "The posting is no longer published."
    await session.flush()
    logger.info(
        "Job expired.",
        extra={"action": "job.expire", "status": "ok", "user_id": user.id, "job_id": job.id},
    )
    return job


async def list_scores(session: AsyncSession, user: User, job_id: int) -> list[JobScore]:
    """The job's scoring history, newest first. Raises if the job is not the user's."""
    job = await get_job(session, user, job_id)
    result = await session.execute(
        select(JobScore)
        .where(JobScore.job_id == job.id, JobScore.user_id == user.id)
        .order_by(JobScore.created_at.desc(), JobScore.id.desc())
    )
    return list(result.scalars().all())


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


async def screen_by_preferences(
    session: AsyncSession, user_id: int, job: Job
) -> PreferenceVerdict:
    """Drop a posting the user already ruled out, before it costs a model call.

    Deliberately a *caller's* decision rather than part of the AI layer: this is
    not a second definition of "skipped" competing with the score threshold, it
    is the question of whether to score the posting at all. Both callers — the
    API's single-job analyse and the engine's search run — go through here, so
    there is one implementation and one wording of the reason.

    A user who has stated nothing rules out nothing, and the reason always
    quotes their own term, so a skipped posting can be argued with.
    """
    rules = await preference_service.rules_for(session, user_id)
    verdict = screen(
        rules,
        title=job.title or "",
        location=job.location,
        workplace_type=job.workplace_type,
    )
    if not verdict.excluded:
        return verdict

    job.status = JobStatus.SKIPPED
    job.skip_reason = verdict.reason
    await session.flush()
    logger.info(
        "Job skipped by the user's stated preferences.",
        extra={
            "action": "job.screen",
            "status": "skipped",
            "user_id": user_id,
            "job_id": job.id,
            "matched_term": verdict.matched_term,
        },
    )
    return verdict


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

    verdict = await screen_by_preferences(session, user.id, job)
    if verdict.excluded:
        await manager.publish(
            user.id,
            make_event(
                EventName.JOB_ANALYZED,
                job_id=job.id,
                message=f"{job.title}: {verdict.reason}",
                level="info",
                data={"skipped": True, "matched_term": verdict.matched_term},
            ),
        )
        return job

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


async def build_recommendations(
    session: AsyncSession, user: User, jobs: Sequence[Job]
) -> dict[int, RecommendationRead]:
    """Why each of these postings — as covered/missing terms, for a whole page.

    The candidate's resume and priorities are read once and reused across the
    rows: this is called with a page of jobs, and one profile query per row
    would be an N+1 for data that cannot differ between them.

    Postings with no description are left out. There is nothing to compare
    against, and an empty split would read as "you match nothing" rather than
    "we have not fetched this posting's text yet".
    """
    if not jobs:
        return {}

    master = await resume_service.build_master(session, user)
    rules = await preference_service.rules_for(session, user.id)
    resume_text = master.searchable()
    vocabulary = master.vocabulary()

    built: dict[int, RecommendationRead] = {}
    for job in jobs:
        if not (job.description or "").strip():
            continue
        result = recommendation.build(
            score=job.score,
            title=job.title or "",
            description=job.description,
            resume_text=resume_text,
            vocabulary=vocabulary,
            priority=rules.priority_technologies,
        )
        built[job.id] = RecommendationRead(
            verdict=result.verdict,
            score=result.score,
            covered=list(result.covered),
            missing=list(result.missing),
            prioritized=list(result.prioritized),
            covered_total=result.covered_total,
            asked_total=result.asked_total,
            coverage_pct=result.coverage_pct,
            has_evidence=result.has_evidence,
        )
    return built


def to_job_read(job: Job, *, recommended: RecommendationRead | None = None) -> JobRead:
    """Build the response model, filling in what the ORM cannot map.

    `application_id`, and the three fields derived from the stored score: the
    verdict band, the score recomputed from the breakdown's own weights, and the
    gap between the two. Deriving them here keeps them impossible to leave stale,
    and costs no migration. A job scored before dimensions carried weights has
    nothing to recompute from and reports `None` rather than a made-up number.

    `recommended` is optional because most callers show a job for a reason
    other than deciding whether to apply to it, and building it costs a read of
    the master resume.
    """
    breakdown = [ScoreDimension.model_validate(row) for row in job.score_breakdown or []]
    weighted = weighted_score(breakdown)
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
        score_breakdown=breakdown,
        score_gates=list(job.score_gates or []),
        verdict=None if job.score is None else verdict_for(job.score),
        weighted_score=weighted,
        score_divergence=(
            None if weighted is None or job.score is None else job.score - weighted
        ),
        skip_reason=job.skip_reason,
        detected_language=job.detected_language,
        posted_at=job.posted_at,
        deadline=job.deadline,
        expired_at=job.expired_at,
        is_stale=is_stale(job),
        created_at=job.created_at,
        search_id=job.search_id,
        application_id=job.application.id if job.application else None,
        recommendation=recommended,
    )


def to_job_detail(job: Job, *, recommended: RecommendationRead | None = None) -> JobDetail:
    return JobDetail(
        **to_job_read(job, recommended=recommended).model_dump(),
        description=job.description,
    )


def to_job_score_read(row: JobScore) -> JobScoreRead:
    """Build one history entry.

    The stored dimensions are re-validated rather than passed through: rows written
    before a field existed read back with its default, exactly as `to_job_read`
    treats `Job.score_breakdown`.
    """
    return JobScoreRead(
        id=row.id,
        job_id=row.job_id,
        overall=row.overall,
        verdict=row.verdict,
        dimensions=[ScoreDimension.model_validate(item) for item in row.dimensions or []],
        gates=list(row.gates or []),
        model=row.model,
        depth=row.depth,
        profile_fingerprint=row.profile_fingerprint,
        created_at=row.created_at,
    )
