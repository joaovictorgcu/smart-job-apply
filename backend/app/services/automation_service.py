"""Policy layer between the API and the automation engine.

This is where the assisted-mode guarantees live. Every path that could reach the
"Submit application" button passes through here, and each one demands an explicit,
separate confirmation from the user:

- searching and scoring never submit anything;
- preparing a form requires `PrepareRequest.confirmed is True` and stops at review;
- submitting requires `SubmitRequest.confirm is True`, an application that really
  is `AWAITING_REVIEW`, and `dry_run` turned off in the user's settings.

The engine re-validates all of it before it clicks anything, so these checks are
fast feedback for the user, not the only line of defence.

Long work is handed to `engine.launch_background`, but only from a response
background task: the engine opens its own session, so it must not start before the
request's transaction has committed. It never receives ORM objects or this
request's session — only identifiers and plain contract objects.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import (
    ConflictError,
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from app.automation.contracts import SearchFilters, SessionState
from app.automation.errors import AutomationError, ThrottleLimitError
from app.automation.throttle import Throttle
from app.config import get_settings
from app.database.base import utcnow
from app.database.session import session_scope
from app.models import (
    Application,
    ApplicationStatus,
    AutomationRun,
    AutomationRunKind,
    AutomationRunStatus,
    JobStatus,
    User,
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

# Users whose browser this process opened, so shutdown can close them.
_session_users: set[int] = set()


def _get_engine() -> Any:
    """Resolve the engine on first use (it pulls in Playwright)."""
    try:
        from app.automation import get_engine
    except ImportError as exc:
        raise AutomationError(f"The automation engine is unavailable: {exc}") from exc

    return get_engine()


async def _call_engine(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Call an engine method, tolerating a synchronous implementation.

    Cheap operations such as `request_stop` are plain functions; the policy layer
    should not have to care which of them are coroutines.
    """
    engine = _get_engine()
    method = getattr(engine, method_name, None)
    if method is None:
        raise AutomationError(f"The automation engine does not implement '{method_name}'.")
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


async def _engine_coroutine(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Single awaitable the engine's task runner can supervise."""
    return await _call_engine(method_name, *args, **kwargs)


# asyncio keeps only a weak reference to a task, so fire-and-forget work needs one.
_detached: set[asyncio.Task[Any]] = set()


def _spawn_detached(coroutine: Coroutine[Any, Any, Any], *, label: str, user_id: int) -> None:
    """Run short engine work that must not go through the run launcher."""

    async def guarded() -> None:
        try:
            await coroutine
        except Exception as exc:
            logger.error(
                f"Detached automation call '{label}' failed.",
                exc_info=exc,
                extra={"action": f"automation.{label}", "status": "error", "user_id": user_id},
            )

    task = asyncio.create_task(guarded())
    _detached.add(task)
    task.add_done_callback(_detached.discard)


def _ensure_engine_free(user_id: int) -> None:
    """Reject a second concurrent run up front, instead of after the response."""
    try:
        engine = _get_engine()
    except AutomationError:
        return  # a missing engine is reported by the call that needs it
    if getattr(engine, "is_busy", None) is not None and engine.is_busy(user_id):
        raise ConflictError(
            "Another automation is already running for this account. "
            "Wait for it to finish or use the stop button."
        )


async def _fail_run(run_id: int, message: str) -> None:
    """Close a run that could never start, so it stops looking active."""
    async with session_scope() as session:
        run = await session.get(AutomationRun, run_id)
        if run is not None and not run.is_terminal:
            run.status = AutomationRunStatus.FAILED
            run.error_message = message
            run.finished_at = utcnow()


async def _launch(
    factory: Callable[[], Coroutine[Any, Any, Any]],
    *,
    label: str,
    user_id: int,
    run_id: int | None = None,
) -> None:
    """Hand the work to the engine's supervised task runner.

    Runs after the response, so the engine's own session sees the committed run.
    """
    try:
        engine = _get_engine()
        engine.launch_background(user_id, factory(), name=label)
        _session_users.add(user_id)
    except Exception as exc:
        message = str(exc) or "The automation could not be started."
        logger.error(
            f"Could not start '{label}'.",
            exc_info=exc,
            extra={"action": label, "status": "error", "user_id": user_id, "run_id": run_id},
        )
        if run_id is not None:
            await _fail_run(run_id, message)
        await manager.publish(
            user_id,
            make_event(
                EventName.AUTOMATION_ERROR,
                run_id=run_id,
                message=message,
                level="error",
                data={"stage": label},
            ),
        )


def _schedule(
    background: BackgroundTasks | None,
    factory: Callable[[], Coroutine[Any, Any, Any]],
    *,
    label: str,
    user_id: int,
    run_id: int | None = None,
) -> None:
    """Start engine work only once the request's transaction has committed.

    A background task registered on the response runs after the session commits and
    after the body has been sent, so the client is not kept waiting and the engine
    can actually see the run row it was told about.
    """
    if background is None:
        # Outside a request (scripts, tests) there is no response to hang it on.
        # `_launch` hands the work to the engine, which keeps its own reference.
        asyncio.get_running_loop().create_task(
            _launch(factory, label=label, user_id=user_id, run_id=run_id)
        )
        return
    background.add_task(_launch, factory, label=label, user_id=user_id, run_id=run_id)


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


async def _active_runs(session: AsyncSession, user: User) -> list[AutomationRun]:
    result = await session.execute(
        select(AutomationRun)
        .where(AutomationRun.user_id == user.id, AutomationRun.status.in_(ACTIVE_RUN_STATUSES))
        .order_by(AutomationRun.id.desc())
    )
    return list(result.scalars().all())


async def _engine_state(user: User) -> SessionState:
    """Current browser state, degraded gracefully when the engine cannot answer."""
    try:
        state = await _call_engine("get_session_state", user.id)
    except (AutomationError, AttributeError) as exc:
        logger.warning(
            "Could not read the automation session state.",
            extra={
                "action": "session.state",
                "status": "unavailable",
                "user_id": user.id,
                "error_type": type(exc).__name__,
            },
        )
        return SessionState()
    return state if isinstance(state, SessionState) else SessionState()


async def session_status(session: AsyncSession, user: User) -> SessionStatus:
    """Browser state + today's counters + guardrails, as the dashboard shows them."""
    user_settings = await user_service.get_or_create_settings(session, user)
    state = await _engine_state(user)
    active = await _active_runs(session, user)
    return SessionStatus(
        browser_open=state.browser_open,
        logged_in=state.logged_in,
        blocked=state.blocked,
        blocked_reason=state.blocked_reason,
        active_run_id=active[0].id if active else None,
        applications_today=await application_service.count_submitted_today(session, user),
        daily_cap=user_settings.daily_cap,
        dry_run=user_settings.dry_run,
        ai_configured=get_settings().ai_enabled,
    )


async def start_session(session: AsyncSession, user: User) -> SessionStatus:
    """Open the browser window. The user logs in there; we never see the password."""
    await _call_engine("start_session", user.id)
    _session_users.add(user.id)
    logger.info(
        "Browser session started.",
        extra={"action": "session.start", "status": "ok", "user_id": user.id},
    )
    return await session_status(session, user)


async def stop_session(session: AsyncSession, user: User) -> SessionStatus:
    """Close the browser window, persisting the session cookies encrypted."""
    await _call_engine("stop_session", user.id)
    _session_users.discard(user.id)
    logger.info(
        "Browser session closed.",
        extra={"action": "session.stop", "status": "ok", "user_id": user.id},
    )
    return await session_status(session, user)


async def build_preview(session: AsyncSession, user: User, job_ids: list[int]) -> PreviewResponse:
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
    if not Throttle(user_settings).within_working_hours():
        warnings.append(
            "The current time is outside the configured working hours "
            f"({user_settings.working_hour_start:02d}:00-{user_settings.working_hour_end:02d}:00)."
        )
    if remaining == 0:
        warnings.append(
            f"Daily cap reached ({submitted_today}/{user_settings.daily_cap}); drafts can be "
            "prepared but nothing can be submitted today."
        )
    elif len(selected) > remaining:
        warnings.append(
            f"{len(selected)} jobs selected but only {remaining} submissions remain today."
        )
    unscored = [job for job in selected if job.score is None]
    if unscored:
        warnings.append(f"{len(unscored)} of the selected jobs have not been analyzed yet.")
    if missing:
        warnings.append(f"{len(missing)} of the selected jobs no longer exist and were ignored.")
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

    # Checked after validation so a malformed request is reported as such.
    _ensure_engine_free(user.id)
    run = await create_run(session, user, AutomationRunKind.SEARCH, search_id=payload.search_id)
    run_id = run.id
    user_id = user.id
    analyze = payload.analyze

    _schedule(
        background,
        lambda: _engine_coroutine("run_search", user_id, run_id, filters, analyze=analyze),
        label="search",
        user_id=user_id,
        run_id=run_id,
    )
    return run


async def start_prepare_run(
    session: AsyncSession,
    user: User,
    payload: PrepareRequest,
    *,
    background: BackgroundTasks | None = None,
) -> AutomationRun:
    """Fill the Easy Apply forms and stop at review. Requires the preview confirmation."""
    if payload.confirmed is not True:
        raise PreconditionFailedError(
            "Preparation requires confirmation: review the preview and send 'confirmed': true."
        )

    jobs = await job_service.get_jobs_by_ids(session, user, payload.job_ids)
    eligible = [job for job in jobs if job.status != JobStatus.APPLIED]
    if not eligible:
        raise ValidationError("None of the selected jobs can be prepared.")
    _ensure_engine_free(user.id)

    run = await create_run(session, user, AutomationRunKind.PREPARE)
    run_id = run.id
    user_id = user.id
    job_ids = [job.id for job in eligible]

    _schedule(
        background,
        lambda: _engine_coroutine("prepare_applications", user_id, run_id, job_ids),
        label="prepare",
        user_id=user_id,
        run_id=run_id,
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
) -> Application:
    """Approve and submit one reviewed application — the only submitting path.

    Refuses unless the user confirmed this exact application, the draft really is
    awaiting review, dry-run is off, and the daily cap and working-hour guardrails
    still allow it. The engine checks every one of these again before it clicks.
    The status stays `AWAITING_REVIEW` here on purpose: the engine moves it to
    `SUBMITTING` when it actually starts, and can put it back on failure.
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
    # against this one application id, right here.
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

    throttle = Throttle(user_settings)
    throttle.assert_within_working_hours()
    submitted_today = await application_service.count_submitted_today(session, user)
    if submitted_today >= user_settings.daily_cap:
        raise ThrottleLimitError(
            f"Daily cap reached: {submitted_today}/{user_settings.daily_cap} applications "
            "submitted today. Try again tomorrow or raise the cap in settings."
        )

    await application_service.approve(session, user, application.id)

    user_id = user.id
    _schedule(
        background,
        lambda: _engine_coroutine("submit_application", user_id, application_id),
        label="submit",
        user_id=user_id,
    )
    logger.info(
        "Submission approved by the user.",
        extra={
            "action": "automation.submit",
            "status": "scheduled",
            "user_id": user_id,
            "application_id": application_id,
        },
    )
    return application


async def stop_all(session: AsyncSession, user: User) -> int:
    """Kill switch: flag the runs, stop the engine cooperatively, then cancel it.

    Returns how many runs were live. The flags are written in this transaction so a
    client that reads `/automation/runs` right after this call sees the truth; the
    engine writes the same flags again from its own session, which is idempotent.
    """
    active = await _active_runs(session, user)
    for run in active:
        run.stop_requested = True
        if run.status == AutomationRunStatus.PENDING:
            # Never picked up, so nothing will ever finish it.
            run.status = AutomationRunStatus.STOPPED
            run.finished_at = utcnow()
    await session.flush()

    try:
        # Immediate and in-memory: the running loop notices at its next step.
        await _call_engine("request_stop", user.id)
    except (AutomationError, AttributeError) as exc:
        logger.warning(
            "The engine could not be notified; the run flags alone will stop it.",
            extra={
                "action": "automation.stop",
                "status": "degraded",
                "user_id": user.id,
                "error_type": type(exc).__name__,
            },
        )
        await manager.publish(
            user.id,
            make_event(
                EventName.AUTOMATION_STOPPED,
                message="Stop requested by the user.",
                level="warning",
                data={"runs_flagged": len(active)},
            ),
        )
    else:
        # Deliberately not through `_launch`: the engine's run launcher refuses to
        # start while a run is in flight, and it clears the stop flag we just set.
        _spawn_detached(_engine_coroutine("stop_all", user.id), label="stop", user_id=user.id)

    logger.warning(
        "Kill switch activated.",
        extra={
            "action": "automation.stop",
            "status": "ok",
            "user_id": user.id,
            "runs_flagged": len(active),
        },
    )
    return len(active)


async def shutdown_engine() -> None:
    """Stop every browser this process opened, on application shutdown."""
    for user_id in list(_session_users):
        try:
            await _call_engine("stop_all", user_id)
            await _call_engine("stop_session", user_id)
        except Exception as exc:
            logger.warning(
                "A browser session did not shut down cleanly.",
                extra={
                    "action": "shutdown.engine",
                    "status": "degraded",
                    "user_id": user_id,
                    "error_type": type(exc).__name__,
                },
            )
    _session_users.clear()


def to_run_read(run: AutomationRun) -> AutomationRunRead:
    return AutomationRunRead.model_validate(run)
