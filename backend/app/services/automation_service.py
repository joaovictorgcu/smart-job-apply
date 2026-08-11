"""Policy layer between the API and the automation engine.

This is where the assisted-mode guarantees live. Every path that could touch the
"Submit application" button passes through here, and every one of them requires an
explicit, separate confirmation from the user:

- searching and scoring never submit anything;
- preparing a form requires `PrepareRequest.confirmed is True` and stops at review;
- submitting requires `SubmitRequest.confirm is True`, an application that is
  actually `AWAITING_REVIEW`, and `dry_run` turned off in the user's settings.

The engine is imported lazily and only ever receives identifiers and plain
contract objects — never ORM instances and never the request's session, because it
runs after the response and opens its own session.

Expected engine contract (`app.automation.get_engine()`):
    await engine.start_session(user_id) -> SessionState
    await engine.stop_session(user_id) -> SessionState
    await engine.get_session_state(user_id) -> SessionState
    await engine.run_search(user_id, run_id, filters, analyze=True) -> None
    await engine.prepare_application(user_id, run_id, job_ids) -> None
    await engine.submit_application(user_id, run_id, application_id) -> None
    engine.request_stop(user_id) -> None
    engine.stop_all() -> None
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFoundError, PreconditionFailedError, ValidationError
from app.automation.contracts import SearchFilters, SessionState
from app.automation.errors import AutomationError, ThrottleLimitError
from app.config import get_settings
from app.database.base import utcnow
from app.models import (
    Application,
    ApplicationStatus,
    AutomationRun,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
    User,
    UserSettings,
)
from app.observability import EventName, get_logger, make_event
from app.schemas.automation import (
    AutomationRunRead,
    PrepareRequest,
    PreviewResponse,
    SearchRunRequest,
    SubmitRequest,
)
from app.schemas.user import SessionStatus
from app.services import application_service, job_service, search_service, user_service
from app.websocket.manager import manager

logger = get_logger(__name__)

ACTIVE_RUN_STATUSES = (
    AutomationRunStatus.PENDING,
    AutomationRunStatus.RUNNING,
    AutomationRunStatus.PAUSED,
)

# asyncio only keeps a weak reference to a task, so a detached run would be
# garbage collected mid-flight without this.
_detached: set[asyncio.Task[Any]] = set()


def _get_engine() -> Any:
    """Import the engine on first use (it pulls in Playwright)."""
    from app.automation import get_engine

    return get_engine()


async def _call_engine(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Call an engine method, tolerating a synchronous implementation.

    Cheap operations such as `request_stop` may legitimately be plain functions;
    the policy layer should not care which.
    """
    engine = _get_engine()
    method = getattr(engine, method_name, None)
    if method is None:
        raise AutomationError(f"The automation engine does not implement '{method_name}'.")
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _detach(factory: Callable[[], Coroutine[Any, Any, Any]], *, label: str, user_id: int) -> None:
    task = asyncio.create_task(_guarded(factory(), label=label, user_id=user_id))
    _detached.add(task)
    task.add_done_callback(_detached.discard)


async def _guarded(
    coroutine: Coroutine[Any, Any, Any], *, label: str, user_id: int
) -> None:
    """Run detached engine work, making sure a failure is never silent."""
    try:
        await coroutine
    except Exception as exc:  # a detached task has nobody to propagate to
        logger.error(
            f"Background automation '{label}' failed.",
            exc_info=exc,
            extra={"action": label, "status": "error", "user_id": user_id},
        )
        await manager.publish(
            user_id,
            make_event(
                EventName.AUTOMATION_ERROR,
                message=str(exc) or "The automation failed.",
                level="error",
                data={"stage": label, "error_type": type(exc).__name__},
            ),
        )


def _schedule(
    background: BackgroundTasks | None,
    factory: Callable[[], Coroutine[Any, Any, Any]],
    *,
    label: str,
    user_id: int,
) -> None:
    """Start engine work only after the request's transaction has committed.

    A background task registered on the response runs after the session commits,
    so the engine (which opens its own session) can actually see the run row. The
    task itself only spawns a detached task, so the HTTP connection is released
    immediately instead of being held for the whole run.
    """
    if background is None:
        _detach(factory, label=label, user_id=user_id)
        return
    background.add_task(_detach, factory, label=label, user_id=user_id)


async def create_run(
    session: AsyncSession,
    user: User,
    kind: AutomationRunKind,
    *,
    search_id: int | None = None,
    dry_run: bool | None = None,
) -> AutomationRun:
    """Create the audit record every automation run is tracked by."""
    if dry_run is None:
        user_settings = await user_service.get_or_create_settings(session, user)
        dry_run = user_settings.dry_run
    run = AutomationRun(
        user_id=user.id,
        search_id=search_id,
        kind=kind,
        status=AutomationRunStatus.PENDING,
        dry_run=dry_run,
        checkpoint={},
    )
    session.add(run)
    await session.flush()
    logger.info(
        "Automation run created.",
        extra={
            "action": "run.create",
            "status": "ok",
            "user_id": user.id,
            "run_id": run.id,
            "kind": str(kind),
            "dry_run": dry_run,
        },
    )
    return run


async def list_runs(session: AsyncSession, user: User, *, limit: int = 20) -> list[AutomationRun]:
    result = await session.execute(
        select(AutomationRun)
        .where(AutomationRun.user_id == user.id)
        .order_by(AutomationRun.created_at.desc(), AutomationRun.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_run(session: AsyncSession, user: User, run_id: int) -> AutomationRun:
    result = await session.execute(
        select(AutomationRun).where(AutomationRun.id == run_id, AutomationRun.user_id == user.id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise NotFoundError("Automation run not found.")
    return run


async def _active_run_id(session: AsyncSession, user: User) -> int | None:
    result = await session.execute(
        select(AutomationRun.id)
        .where(AutomationRun.user_id == user.id, AutomationRun.status.in_(ACTIVE_RUN_STATUSES))
        .order_by(AutomationRun.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _within_working_hours(user_settings: UserSettings, *, now: datetime | None = None) -> bool:
    hour = (now or datetime.now()).hour
    return user_settings.working_hour_start <= hour < user_settings.working_hour_end


async def _engine_state(user: User) -> SessionState:
    """Current browser state, degraded gracefully when the engine cannot answer."""
    try:
        state = await _call_engine("get_session_state", user.id)
    except (AutomationError, ImportError, AttributeError) as exc:
        logger.warning(
            "Could not read the automation session state.",
            extra={"action": "session.state", "status": "unavailable", "user_id": user.id,
                   "error_type": type(exc).__name__},
        )
        return SessionState()
    if isinstance(state, SessionState):
        return state
    return SessionState()


async def session_status(session: AsyncSession, user: User) -> SessionStatus:
    """Browser state + today's counters + guardrails, as the dashboard shows them."""
    user_settings = await user_service.get_or_create_settings(session, user)
    state = await _engine_state(user)
    return SessionStatus(
        browser_open=state.browser_open,
        logged_in=state.logged_in,
        blocked=state.blocked,
        blocked_reason=state.blocked_reason,
        active_run_id=await _active_run_id(session, user),
        applications_today=await application_service.count_submitted_today(session, user),
        daily_cap=user_settings.daily_cap,
        dry_run=user_settings.dry_run,
        ai_configured=get_settings().ai_enabled,
    )


async def start_session(session: AsyncSession, user: User) -> SessionStatus:
    """Open the browser window. The user logs in there; we never see the password."""
    await _call_engine("start_session", user.id)
    logger.info(
        "Browser session requested.",
        extra={"action": "session.start", "status": "ok", "user_id": user.id},
    )
    return await session_status(session, user)


async def stop_session(session: AsyncSession, user: User) -> SessionStatus:
    await _call_engine("stop_session", user.id)
    logger.info(
        "Browser session closed.",
        extra={"action": "session.stop", "status": "ok", "user_id": user.id},
    )
    return await session_status(session, user)


async def build_preview(
    session: AsyncSession, user: User, job_ids: list[int]
) -> PreviewResponse:
    """Describe exactly what a prepare run would do, before it does anything."""
    user_settings = await user_service.get_or_create_settings(session, user)
    jobs = await job_service.get_jobs_by_ids(session, user, job_ids)
    found_ids = {job.id for job in jobs}
    missing = [job_id for job_id in job_ids if job_id not in found_ids]

    already_applied = [job for job in jobs if job.status == JobStatus.APPLIED]
    below_threshold = [
        job
        for job in jobs
        if job.status != JobStatus.APPLIED
        and job.score is not None
        and job.score < user_settings.min_score
    ]
    excluded = {job.id for job in already_applied} | {job.id for job in below_threshold}
    selected = [job for job in jobs if job.id not in excluded]

    submitted_today = await application_service.count_submitted_today(session, user)
    remaining = max(0, user_settings.daily_cap - submitted_today)

    warnings: list[str] = []
    if user_settings.dry_run:
        warnings.append("Dry-run mode is ON — nothing will be submitted.")
    if not get_settings().ai_enabled:
        warnings.append("AI is not configured; scores and answers will not be generated.")

    state = await _engine_state(user)
    if not state.browser_open:
        warnings.append("The browser is not open; start the session first.")
    elif not state.logged_in:
        warnings.append("LinkedIn session is not connected; log in in the browser window.")
    if state.blocked:
        warnings.append(
            f"Automation is blocked: {state.blocked_reason or 'security verification detected'}."
        )
    if not _within_working_hours(user_settings):
        warnings.append(
            "Current time is outside configured working hours "
            f"({user_settings.working_hour_start}:00-{user_settings.working_hour_end}:00)."
        )
    if remaining == 0:
        warnings.append(
            f"Daily cap reached ({submitted_today}/{user_settings.daily_cap}); "
            "drafts can be prepared but nothing can be submitted today."
        )
    elif len(selected) > remaining:
        warnings.append(
            f"{len(selected)} jobs selected but only {remaining} submissions remain today."
        )
    unscored = [job for job in selected if job.score is None]
    if unscored:
        warnings.append(f"{len(unscored)} selected jobs have not been analyzed yet.")
    if missing:
        warnings.append(f"{len(missing)} selected jobs no longer exist and were ignored.")
    profile = await user_service.get_or_create_profile(session, user)
    if not profile.resume_filename:
        warnings.append("No resume uploaded; the form may not be completable.")

    return PreviewResponse(
        jobs_to_process=len(selected),
        already_applied=len(already_applied),
        below_threshold=len(below_threshold),
        remaining_today=remaining,
        daily_cap=user_settings.daily_cap,
        dry_run=user_settings.dry_run,
        requires_confirmation=True,
        jobs=[job_service.to_job_read(job) for job in selected],
        warnings=warnings,
    )


async def start_search_run(
    session: AsyncSession,
    user: User,
    payload: SearchRunRequest,
    *,
    background: BackgroundTasks | None = None,
) -> AutomationRun:
    """Search (and optionally score) jobs. This path never submits anything."""
    filters: SearchFilters
    if payload.search_id is not None:
        search = await search_service.get_search(session, user, payload.search_id)
        filters = search_service.to_filters(search, max_results=payload.max_results)
        if payload.keywords:
            filters.keywords = payload.keywords
        if payload.location:
            filters.location = payload.location
        if payload.remote_filter:
            filters.remote_filter = payload.remote_filter
        if payload.date_posted:
            filters.date_posted = payload.date_posted
        if payload.experience_levels:
            filters.experience_levels = list(payload.experience_levels)
        await search_service.touch_last_run(session, user, search.id)
    else:
        if not payload.keywords:
            raise ValidationError("Provide either 'search_id' or 'keywords'.")
        filters = SearchFilters(
            keywords=payload.keywords,
            location=payload.location,
            remote_filter=payload.remote_filter,
            date_posted=payload.date_posted,
            experience_levels=list(payload.experience_levels),
            easy_apply_only=True,
            max_results=payload.max_results,
        )

    run = await create_run(
        session, user, AutomationRunKind.SEARCH, search_id=payload.search_id
    )
    run_id = run.id
    user_id = user.id
    analyze = payload.analyze

    _schedule(
        background,
        lambda: _call_engine("run_search", user_id, run_id, filters, analyze=analyze),
        label="automation.search",
        user_id=user_id,
    )
    return run


async def start_prepare_run(
    session: AsyncSession,
    user: User,
    payload: PrepareRequest,
    *,
    background: BackgroundTasks | None = None,
) -> AutomationRun:
    """Fill the Easy Apply form and stop at review. Requires the preview confirmation."""
    if payload.confirmed is not True:
        raise PreconditionFailedError(
            "Preparation requires confirmation: review the preview and send 'confirmed': true."
        )

    jobs = await job_service.get_jobs_by_ids(session, user, payload.job_ids)
    eligible = [job for job in jobs if job.status != JobStatus.APPLIED]
    if not eligible:
        raise ValidationError("None of the selected jobs can be prepared.")

    run = await create_run(session, user, AutomationRunKind.PREPARE)
    run_id = run.id
    user_id = user.id
    job_ids = [job.id for job in eligible]

    _schedule(
        background,
        lambda: _call_engine("prepare_application", user_id, run_id, job_ids),
        label="automation.prepare",
        user_id=user_id,
    )
    logger.info(
        "Preparation confirmed by the user.",
        extra={
            "action": "automation.prepare",
            "status": "scheduled",
            "user_id": user_id,
            "run_id": run_id,
            "jobs": len(job_ids),
        },
    )
    return run


async def submit_application(
    session: AsyncSession,
    user: User,
    application_id: int,
    payload: SubmitRequest,
    *,
    background: BackgroundTasks | None = None,
) -> tuple[Application, AutomationRun]:
    """Submit one reviewed application. The only path that can click "Submit".

    Refuses unless the user confirmed this exact application, the draft is really
    awaiting review, dry-run is off and the daily cap still has room.
    """
    if payload.confirm is not True:
        raise PreconditionFailedError(
            "Submission requires explicit confirmation: send 'confirm': true."
        )

    user_settings = await user_service.get_or_create_settings(session, user)
    if user_settings.dry_run:
        raise PreconditionFailedError(
            "Dry-run mode is ON. Turn it off in settings to submit a real application."
        )
    # Assisted mode is not negotiable through the payload: the approval is recorded
    # against the application itself, right here, and only for this one id.
    if get_settings().assisted_mode_only and not user_settings.require_manual_approval:
        raise PreconditionFailedError(
            "This deployment requires manual approval; re-enable it in settings."
        )

    application = await application_service.get_application(session, user, application_id)
    if application.status != ApplicationStatus.AWAITING_REVIEW:
        raise PreconditionFailedError(
            "Only an application awaiting review can be submitted "
            f"(current status: '{application.status}')."
        )

    submitted_today = await application_service.count_submitted_today(session, user)
    if submitted_today >= user_settings.daily_cap:
        raise ThrottleLimitError(
            f"Daily cap reached ({submitted_today}/{user_settings.daily_cap}). "
            "Try again tomorrow or raise the cap in settings."
        )

    run = await create_run(session, user, AutomationRunKind.SUBMIT, dry_run=False)
    await application_service.approve(session, user, application.id, run_id=run.id)
    application.status = ApplicationStatus.SUBMITTING
    await session.flush()

    run_id = run.id
    user_id = user.id
    _schedule(
        background,
        lambda: _call_engine("submit_application", user_id, run_id, application_id),
        label="automation.submit",
        user_id=user_id,
    )
    logger.info(
        "Submission approved by the user.",
        extra={
            "action": "automation.submit",
            "status": "scheduled",
            "user_id": user_id,
            "run_id": run_id,
            "application_id": application_id,
        },
    )
    return application, run


async def stop_all(session: AsyncSession, user: User) -> int:
    """Kill switch: flag every live run and tell the engine to stand down.

    Returns how many runs were flagged. Runs cooperatively: the engine checks
    `stop_requested` between steps, so nothing is left half-filled.
    """
    result = await session.execute(
        select(AutomationRun).where(
            AutomationRun.user_id == user.id,
            AutomationRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    )
    runs = list(result.scalars().all())
    for run in runs:
        run.stop_requested = True
        if run.status == AutomationRunStatus.PENDING:
            run.status = AutomationRunStatus.STOPPED
            run.finished_at = utcnow()
    await session.flush()

    try:
        await _call_engine("request_stop", user.id)
    except (AutomationError, ImportError, AttributeError) as exc:
        # The database flag alone already stops the run at its next checkpoint.
        logger.warning(
            "The engine could not be notified of the stop request.",
            extra={"action": "automation.stop", "status": "degraded", "user_id": user.id,
                   "error_type": type(exc).__name__},
        )

    await manager.publish(
        user.id,
        make_event(
            EventName.AUTOMATION_STOPPED,
            message="Stop requested by the user. Automation is standing down.",
            level="warning",
            data={"runs_flagged": len(runs)},
        ),
    )
    logger.warning(
        "Kill switch activated.",
        extra={
            "action": "automation.stop",
            "status": "ok",
            "user_id": user.id,
            "runs_flagged": len(runs),
        },
    )
    return len(runs)


async def shutdown_engine() -> None:
    """Close every browser session on application shutdown."""
    for task in list(_detached):
        task.cancel()
    try:
        await _call_engine("stop_all")
    except (AutomationError, ImportError, AttributeError, RuntimeError) as exc:
        logger.warning(
            "The automation engine did not shut down cleanly.",
            extra={"action": "shutdown.engine", "status": "degraded",
                   "error_type": type(exc).__name__},
        )


def to_run_read(run: AutomationRun) -> AutomationRunRead:
    return AutomationRunRead.model_validate(run)
