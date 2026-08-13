"""Applications: the draft that waits for a human before anything is submitted."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import NotFoundError, PreconditionFailedError
from app.database.base import utcnow
from app.models import (
    Application,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationOutcome,
    ApplicationStatus,
    Job,
    JobStatus,
    User,
)
from app.observability import get_logger, record_event
from app.schemas.application import (
    ApplicationCard,
    ApplicationDetail,
    ApplicationEventOut,
    ApplicationRead,
    ApplicationUpdate,
)
from app.services import job_service

logger = get_logger(__name__)

EDITABLE_STATUSES = {ApplicationStatus.DRAFT, ApplicationStatus.AWAITING_REVIEW}


def _application_query() -> Select[tuple[Application]]:
    return select(Application).options(
        selectinload(Application.job).selectinload(Job.application),
        selectinload(Application.events),
    )


def start_of_day(reference: datetime | None = None) -> datetime:
    """Midnight UTC of the reference day.

    Counters are anchored to UTC so a daily cap cannot be reset by changing the
    machine's timezone.
    """
    moment = reference or utcnow()
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


async def get_application(session: AsyncSession, user: User, application_id: int) -> Application:
    result = await session.execute(
        _application_query().where(Application.id == application_id, Application.user_id == user.id)
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise NotFoundError("Application not found.")
    return application


async def get_or_create_for_job(session: AsyncSession, user: User, job_id: int) -> Application:
    """One application per job (enforced by a unique constraint)."""
    job = await job_service.get_job(session, user, job_id)
    result = await session.execute(
        _application_query().where(Application.job_id == job.id, Application.user_id == user.id)
    )
    application = result.scalar_one_or_none()
    if application is not None:
        return application

    application = Application(
        user_id=user.id,
        job_id=job.id,
        status=ApplicationStatus.DRAFT,
        screening_answers=[],
    )
    session.add(application)
    await session.flush()
    logger.info(
        "Application draft created.",
        extra={
            "action": "application.create",
            "status": "ok",
            "user_id": user.id,
            "job_id": job.id,
            "application_id": application.id,
        },
    )
    return application


async def list_applications(
    session: AsyncSession,
    user: User,
    *,
    status: ApplicationStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Application], int]:
    conditions = [Application.user_id == user.id]
    if status is not None:
        conditions.append(Application.status == status)

    total_result = await session.execute(
        select(func.count()).select_from(Application).where(*conditions)
    )
    result = await session.execute(
        select(Application)
        .where(*conditions)
        .order_by(Application.updated_at.desc(), Application.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total_result.scalar_one())


async def update_draft(
    session: AsyncSession, user: User, application_id: int, payload: ApplicationUpdate
) -> Application:
    """Apply the reviewer's edits to a draft. Never changes the status."""
    application = await get_application(session, user, application_id)
    if application.status not in EDITABLE_STATUSES:
        raise PreconditionFailedError(
            f"An application with status '{application.status}' can no longer be edited."
        )

    changes = payload.model_dump(exclude_unset=True)
    if "cover_letter" in changes:
        application.cover_letter = payload.cover_letter
    if payload.screening_answers is not None:
        # Provenance is decided here rather than trusted from the request: an
        # answer whose text differs from the stored one is the user's wording now,
        # whatever the client claims its source is.
        previous = {
            str(stored.get("field_id") or stored.get("question")): str(stored.get("answer") or "")
            for stored in (application.screening_answers or [])
        }
        serialised: list[dict[str, Any]] = []
        for answer in payload.screening_answers:
            row = answer.model_dump(mode="json")
            key = str(answer.field_id or answer.question)
            if key in previous and previous[key] != answer.answer:
                row["source"] = "user"
            serialised.append(row)

        # The column is plain JSON: Pydantic objects must be serialised first or
        # SQLAlchemy cannot persist them.
        application.screening_answers = serialised
        application.needs_human_input = any(
            answer.needs_review for answer in payload.screening_answers
        )

    await session.flush()
    await record_event(
        session,
        application_id=application.id,
        event_type=ApplicationEventType.USER_EDITED,
        message="The user edited the application before approval.",
        payload={"fields": sorted(changes)},
        job_id=application.job_id,
        user_id=user.id,
    )
    return application


async def approve(
    session: AsyncSession, user: User, application_id: int, *, run_id: int | None = None
) -> Application:
    """Record the explicit human approval. Submission is still a separate step."""
    application = await get_application(session, user, application_id)
    if application.status != ApplicationStatus.AWAITING_REVIEW:
        raise PreconditionFailedError(
            "Only an application awaiting review can be approved "
            f"(current status: '{application.status}')."
        )
    application.approved_at = utcnow()
    await session.flush()
    await record_event(
        session,
        application_id=application.id,
        event_type=ApplicationEventType.USER_APPROVED,
        message="The user approved the submission.",
        run_id=run_id,
        job_id=application.job_id,
        user_id=user.id,
    )
    return application


async def mark_submitted(
    session: AsyncSession,
    user: User,
    application_id: int,
    *,
    was_dry_run: bool = False,
    run_id: int | None = None,
) -> Application:
    """Flag the application (and its job) as submitted."""
    application = await get_application(session, user, application_id)
    application.status = ApplicationStatus.SUBMITTED
    application.submitted_at = utcnow()
    application.was_dry_run = was_dry_run
    application.error_message = None
    # A submitted application enters the pipeline board at APPLIED, waiting for the
    # user to record what happens next (interview, offer, rejection).
    if application.outcome is None:
        application.outcome = ApplicationOutcome.APPLIED
        application.outcome_updated_at = utcnow()
    if application.job is not None:
        application.job.status = JobStatus.APPLIED
    await session.flush()
    await record_event(
        session,
        application_id=application.id,
        event_type=ApplicationEventType.SUBMITTED,
        message="Application submitted." if not was_dry_run else "Dry run: nothing was submitted.",
        payload={"dry_run": was_dry_run},
        run_id=run_id,
        job_id=application.job_id,
        user_id=user.id,
    )
    return application


async def list_board(session: AsyncSession, user: User) -> list[Application]:
    """Submitted applications, with their job, for the pipeline board.

    Most recently moved first, so a card the user just dragged stays near the top
    of its column.
    """
    result = await session.execute(
        select(Application)
        .options(selectinload(Application.job))
        .where(
            Application.user_id == user.id,
            Application.status == ApplicationStatus.SUBMITTED,
        )
        .order_by(
            Application.outcome_updated_at.desc().nullslast(),
            Application.submitted_at.desc(),
            Application.id.desc(),
        )
    )
    return list(result.scalars().all())


async def set_outcome(
    session: AsyncSession,
    user: User,
    application_id: int,
    outcome: ApplicationOutcome,
    *,
    note: str | None = None,
) -> Application:
    """Record the real-world outcome of a submitted application.

    Only a submitted application has an outcome to track — an unsubmitted draft is
    rejected, since the board is about what happened *after* applying.
    """
    application = await get_application(session, user, application_id)
    if application.status != ApplicationStatus.SUBMITTED:
        raise PreconditionFailedError(
            "Only a submitted application has an outcome to track "
            f"(current status: '{application.status}')."
        )
    # `outcome` on the ORM row reads back as a plain string (String column), so it
    # is already the enum value; the incoming `outcome` is the parsed enum.
    previous = application.outcome
    application.outcome = outcome
    application.outcome_updated_at = utcnow()
    if note is not None:
        application.outcome_note = note or None
    await session.flush()
    await record_event(
        session,
        application_id=application.id,
        event_type=ApplicationEventType.OUTCOME_CHANGED,
        message=f"Outcome set to {outcome.value}.",
        payload={"from": str(previous) if previous else None, "to": outcome.value},
        job_id=application.job_id,
        user_id=user.id,
    )
    return application


async def discard(
    session: AsyncSession, user: User, application_id: int, *, reason: str | None = None
) -> Application:
    application = await get_application(session, user, application_id)
    if application.status == ApplicationStatus.SUBMITTED:
        raise PreconditionFailedError("A submitted application cannot be discarded.")
    application.status = ApplicationStatus.DISCARDED
    application.needs_human_input = False
    await session.flush()
    await record_event(
        session,
        application_id=application.id,
        event_type=ApplicationEventType.DISCARDED,
        message=reason or "The user discarded the application.",
        job_id=application.job_id,
        user_id=user.id,
    )
    return application


async def export_csv(session: AsyncSession, user: User) -> str:
    """The user's application history as CSV, newest first.

    Job columns are denormalised into each row so the file stands on its own
    outside the app. Nothing leaves through here that the list endpoints do not
    already expose.
    """
    result = await session.execute(
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.user_id == user.id)
        .order_by(Application.created_at.desc(), Application.id.desc())
    )
    applications = list(result.scalars().all())

    def stamp(moment: datetime | None) -> str:
        return moment.isoformat() if moment else ""

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "application_id",
            "job_title",
            "company",
            "location",
            "job_url",
            "score",
            "status",
            "outcome",
            "outcome_note",
            "was_dry_run",
            "created_at",
            "approved_at",
            "submitted_at",
            "outcome_updated_at",
        ]
    )
    for application in applications:
        job = application.job
        writer.writerow(
            [
                application.id,
                job.title if job else "",
                job.company if job else "",
                (job.location if job else None) or "",
                (job.url if job else None) or "",
                job.score if job and job.score is not None else "",
                str(application.status),
                str(application.outcome) if application.outcome else "",
                application.outcome_note or "",
                "true" if application.was_dry_run else "false",
                stamp(application.created_at),
                stamp(application.approved_at),
                stamp(application.submitted_at),
                stamp(application.outcome_updated_at),
            ]
        )
    return buffer.getvalue()


async def list_events(
    session: AsyncSession, user: User, application_id: int
) -> list[ApplicationEvent]:
    # Resolve through the application so the events stay scoped to the owner.
    application = await get_application(session, user, application_id)
    result = await session.execute(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == application.id)
        .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
    )
    return list(result.scalars().all())


async def count_submitted_today(session: AsyncSession, user: User) -> int:
    """Submissions since midnight UTC — the number the daily cap is checked against."""
    result = await session.execute(
        select(func.count())
        .select_from(Application)
        .where(
            Application.user_id == user.id,
            Application.status == ApplicationStatus.SUBMITTED,
            Application.submitted_at >= start_of_day(),
        )
    )
    return int(result.scalar_one())


async def count_by_status(session: AsyncSession, user: User, status: ApplicationStatus) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Application)
        .where(Application.user_id == user.id, Application.status == status)
    )
    return int(result.scalar_one())


async def submitted_last_days(session: AsyncSession, user: User, days: int = 7) -> dict[str, int]:
    """Submissions per day (ISO date -> count) for the last `days` days."""
    since = start_of_day() - timedelta(days=days - 1)
    day = func.date(Application.submitted_at)
    result = await session.execute(
        select(day, func.count())
        .where(
            Application.user_id == user.id,
            Application.status == ApplicationStatus.SUBMITTED,
            Application.submitted_at >= since,
        )
        .group_by(day)
    )
    return {str(bucket): int(count) for bucket, count in result.all() if bucket is not None}


def to_application_read(application: Application) -> ApplicationRead:
    return ApplicationRead.model_validate(application)


def to_application_card(application: Application) -> ApplicationCard:
    """A board card. The job is expected to be eagerly loaded (see `list_board`)."""
    job = application.job
    return ApplicationCard(
        id=application.id,
        job_id=application.job_id,
        title=job.title if job else "(job removed)",
        company=job.company if job else "",
        location=job.location if job else None,
        score=job.score if job else None,
        outcome=application.outcome or ApplicationOutcome.APPLIED,
        submitted_at=application.submitted_at,
        outcome_updated_at=application.outcome_updated_at,
    )


def to_application_detail(application: Application) -> ApplicationDetail:
    """Build the detail payload from eagerly loaded relationships."""
    return ApplicationDetail(
        **to_application_read(application).model_dump(),
        job=job_service.to_job_read(application.job) if application.job else None,
        events=[ApplicationEventOut.model_validate(event) for event in application.events],
    )
