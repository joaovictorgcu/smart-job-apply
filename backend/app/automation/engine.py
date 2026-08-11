"""The automation orchestrator.

`AutomationEngine` is the only place where the browser, the AI layer and the
database meet. It owns one `LinkedInBrowserService` per user, serializes browser
work with a per-user lock, persists progress into `AutomationRun.checkpoint` so a
run can be resumed, and publishes every state change to the dashboard.

Assisted mode is enforced here, not in the UI:

* `prepare_application` fills the form and leaves it at the review step with
  `status = AWAITING_REVIEW`. In dry-run mode it never opens the real modal.
* `submit_application` is the ONLY path that reaches the submit button, and it
  refuses unless the application is awaiting review, dry run is off, the user
  approved it (`approved_at`), the daily cap is not reached and we are inside the
  configured working hours.
* A `SecurityCheckpointError` anywhere turns the run into `BLOCKED` and stops the
  session. We never try to get past a challenge.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import re
from collections.abc import AsyncIterator, Awaitable, Coroutine, Iterable, Sequence
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.schemas import JobAnalysis, ScreeningAnswer
from app.auth.crypto import DecryptionError, decrypt_json, encrypt_json
from app.automation.contracts import (
    ApplicationDraft,
    FormAnswer,
    FormQuestion,
    JobPosting,
    ProfileContext,
    SearchFilters,
    SessionState,
)
from app.automation.errors import (
    AutomationError,
    EasyApplyUnavailableError,
    SecurityCheckpointError,
    StopRequestedError,
)
from app.automation.linkedin.search import PAGE_SIZE
from app.automation.linkedin.service import LinkedInBrowserService
from app.automation.throttle import Throttle
from app.config import get_settings
from app.database.base import utcnow
from app.database.session import session_scope
from app.models import (
    AnswerConfidence,
    Application,
    ApplicationEventType,
    ApplicationStatus,
    AutomationRun,
    AutomationRunStatus,
    Job,
    JobStatus,
    LinkedInAccount,
    Profile,
    User,
    UserSettings,
)
from app.observability import EventName, get_logger, make_event, record_event, to_live_event
from app.websocket.manager import manager

logger = get_logger(__name__)

# --- AI layer seam -------------------------------------------------------
# `app.ai.*` is owned by another module and its exact entry-point names are
# resolved at call time. Everything degrades gracefully: without a reachable AI
# function, jobs stay unscored and applications are prepared without a cover
# letter instead of the run failing.
_SCORING_TARGETS: tuple[tuple[str, str], ...] = (
    ("app.ai.scoring", "analyze_job"),
    ("app.ai.scoring", "score_job"),
    ("app.ai", "analyze_job"),
)
_COVER_LETTER_TARGETS: tuple[tuple[str, str], ...] = (
    ("app.ai.cover_letter", "generate_cover_letter"),
    ("app.ai.letters", "generate_cover_letter"),
    ("app.ai.scoring", "generate_cover_letter"),
    ("app.ai", "generate_cover_letter"),
)
_SCREENING_TARGETS: tuple[tuple[str, str], ...] = (
    ("app.ai.screening", "answer_screening_questions"),
    ("app.ai.screening", "answer_questions"),
    ("app.ai.scoring", "answer_screening_questions"),
    ("app.ai", "answer_screening_questions"),
)

_EMAIL_HINTS = ("email", "e-mail")
_PHONE_HINTS = ("phone", "telefone", "celular", "mobile")
_FIRST_NAME_HINTS = ("first name", "given name", "nome")
_LAST_NAME_HINTS = ("last name", "surname", "family name", "sobrenome")
_LOCATION_HINTS = ("city", "location", "cidade", "localidade", "where are you")
_EXPERIENCE_HINTS = ("years of experience", "anos de experiência", "anos de experiencia")
_FULL_NAME_HINTS = ("full name", "nome completo")


class AutomationEngine:
    """One instance per process; use `get_engine()`."""

    def __init__(self) -> None:
        settings = get_settings()
        self._semaphore = asyncio.Semaphore(max(1, settings.max_concurrent_sessions))
        self._services: dict[int, LinkedInBrowserService] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._tasks: dict[int, asyncio.Task[Any]] = {}
        self._detached: set[asyncio.Task[Any]] = set()
        self._stop_requested: set[int] = set()
        self._ai_cache: dict[str, Any] = {}

    # --- Concurrency ------------------------------------------------------

    def _lock(self, user_id: int) -> asyncio.Lock:
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
        return lock

    @asynccontextmanager
    async def _exclusive(self, user_id: int) -> AsyncIterator[None]:
        """One browser action at a time per user, bounded globally."""
        async with self._semaphore, self._lock(user_id):
            yield

    def is_busy(self, user_id: int) -> bool:
        task = self._tasks.get(user_id)
        return task is not None and not task.done()

    def launch_background(
        self, user_id: int, coro: Coroutine[Any, Any, Any], *, name: str = "automation"
    ) -> asyncio.Task[Any]:
        """Run a long automation as a task so the HTTP request can return."""
        if self.is_busy(user_id):
            coro.close()
            raise AutomationError(
                "Another automation is already running for this user. Stop it first."
            )
        # Starting new work is the one action that clears a previous kill switch;
        # the runs themselves never clear it, so a stop requested between launch
        # and first step is still honoured.
        self.clear_stop(user_id)
        task = asyncio.create_task(self._supervise(user_id, coro, name), name=f"{name}:{user_id}")
        self._tasks[user_id] = task
        return task

    async def _supervise(self, user_id: int, coro: Coroutine[Any, Any, Any], name: str) -> None:
        """Never let a background task die silently."""
        try:
            await coro
        except asyncio.CancelledError:
            logger.info(
                "Automation task cancelled.",
                extra={"action": f"engine.{name}", "status": "cancelled", "user_id": user_id},
            )
            raise
        except AutomationError as exc:
            logger.warning(
                "Automation task stopped.",
                extra={
                    "action": f"engine.{name}",
                    "status": "error",
                    "user_id": user_id,
                    "error": str(exc),
                },
            )
        except Exception:
            logger.exception(
                "Unhandled error in an automation task.",
                extra={"action": f"engine.{name}", "status": "error", "user_id": user_id},
            )
        finally:
            if self._tasks.get(user_id) is asyncio.current_task():
                self._tasks.pop(user_id, None)

    def _spawn_detached(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Fire-and-forget bookkeeping that must not be cancelled by the kill switch."""
        task = asyncio.create_task(coro)
        self._detached.add(task)
        task.add_done_callback(self._detached.discard)

    # --- Kill switch ------------------------------------------------------

    def request_stop(self, user_id: int) -> None:
        """Cooperative stop: loops notice it between steps. Safe to call anywhere."""
        self._stop_requested.add(user_id)
        logger.warning(
            "Stop requested.", extra={"action": "engine.request_stop", "user_id": user_id}
        )
        self._spawn_detached(self._flag_runs_stopped(user_id))

    async def stop_all(self, user_id: int) -> None:
        """Kill switch: flag the active runs and cancel the in-flight task.

        The browser is deliberately left open so the user can see where the
        automation stopped; `stop_session` closes it.
        """
        self._stop_requested.add(user_id)
        await self._flag_runs_stopped(user_id)
        task = self._tasks.get(user_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # expected: we asked for it
            except Exception as exc:
                logger.debug(
                    "Cancelled task ended with an error.",
                    extra={"action": "engine.stop_all", "user_id": user_id, "error": str(exc)},
                )
        self._tasks.pop(user_id, None)
        await self._publish(
            user_id,
            EventName.AUTOMATION_STOPPED,
            message="Automation stopped by the user.",
            level="warning",
        )

    async def _flag_runs_stopped(self, user_id: int) -> None:
        async with session_scope() as session:
            stmt = select(AutomationRun).where(
                AutomationRun.user_id == user_id,
                AutomationRun.status.in_(
                    [
                        AutomationRunStatus.PENDING,
                        AutomationRunStatus.RUNNING,
                        AutomationRunStatus.PAUSED,
                    ]
                ),
            )
            for run in (await session.execute(stmt)).scalars():
                run.stop_requested = True

    def clear_stop(self, user_id: int) -> None:
        """Reset the kill switch so new work can start."""
        self._stop_requested.discard(user_id)

    async def _check_stop(self, user_id: int, run_id: int | None) -> None:
        if user_id in self._stop_requested:
            raise StopRequestedError("Automation stopped by the user.")
        if run_id is None:
            return
        async with session_scope() as session:
            requested = await session.scalar(
                select(AutomationRun.stop_requested).where(AutomationRun.id == run_id)
            )
        if requested:
            self._stop_requested.add(user_id)
            raise StopRequestedError("Automation stopped by the user.")

    # --- Session management ----------------------------------------------

    async def start_session(self, user_id: int) -> SessionState:
        """Open the browser and report whether a manual login is still needed."""
        async with self._exclusive(user_id):
            service = self._service(user_id)
            await self._configure_service(user_id, service)
            try:
                state = await service.start()
                if not state.logged_in and await self._restore_cookies(user_id, service):
                    state = await service.start()
                await self._persist_account(user_id, service, state)
            except SecurityCheckpointError as exc:
                await self._handle_checkpoint(user_id, None, exc)
                return SessionState(
                    browser_open=False, logged_in=False, blocked=True, blocked_reason=exc.reason
                )
            await self._publish_session(user_id, state)
            return state

    async def wait_for_manual_login(self, user_id: int, timeout_seconds: int = 300) -> SessionState:
        """Block until the user finishes signing in inside the visible window."""
        async with self._exclusive(user_id):
            service = self._service(user_id)
            state = await service.wait_for_login(timeout_seconds)
            await self._persist_account(user_id, service, state)
            await self._publish_session(user_id, state)
            return state

    async def stop_session(self, user_id: int) -> SessionState:
        """Persist the encrypted session state, then close the browser."""
        service = self._services.pop(user_id, None)
        if service is None:
            state = SessionState()
            await self._publish_session(user_id, state)
            return state

        async with self._exclusive(user_id):
            try:
                storage = await service.export_storage_state()
            except AutomationError as exc:
                storage = None
                logger.warning(
                    "Could not export the LinkedIn session state.",
                    extra={"action": "engine.stop_session", "user_id": user_id, "error": str(exc)},
                )
            if storage is not None:
                async with session_scope() as session:
                    account = await self._account(session, user_id, create=True)
                    account.encrypted_storage_state = encrypt_json(storage)
                    account.is_connected = True
                    account.last_verified_at = utcnow()
            await service.stop()

        state = SessionState()
        await self._publish_session(user_id, state)
        return state

    async def get_session_state(self, user_id: int) -> SessionState:
        service = self._services.get(user_id)
        if service is not None:
            return await service.get_state()
        async with session_scope() as session:
            account = await self._account(session, user_id)
            display_name = account.display_name if account else None
        return SessionState(browser_open=False, logged_in=False, display_name=display_name)

    def _service(self, user_id: int) -> LinkedInBrowserService:
        service = self._services.get(user_id)
        if service is None:
            service = LinkedInBrowserService(user_id)
            self._services[user_id] = service
        return service

    async def _ready_service(self, user_id: int) -> LinkedInBrowserService:
        """A started, signed-in service with fresh throttle and resume settings."""
        service = self._service(user_id)
        await self._configure_service(user_id, service)
        if not service.browser.is_open:
            state = await service.start()
            if not state.logged_in and await self._restore_cookies(user_id, service):
                await service.start()
        return service

    async def _configure_service(self, user_id: int, service: LinkedInBrowserService) -> None:
        throttle = await self._throttle(user_id)
        service.configure(throttle=throttle, resume_path=await self._resume_path(user_id))

    async def _restore_cookies(self, user_id: int, service: LinkedInBrowserService) -> bool:
        async with session_scope() as session:
            account = await self._account(session, user_id)
            token = account.encrypted_storage_state if account else None
        if not token:
            return False
        try:
            state = decrypt_json(token)
        except DecryptionError as exc:
            logger.warning(
                "Stored LinkedIn cookies could not be decrypted; a manual login is required.",
                extra={"action": "engine.restore_cookies", "user_id": user_id, "error": str(exc)},
            )
            return False
        if not isinstance(state, dict):
            return False
        await service.import_storage_state(state)
        return True

    async def _persist_account(
        self, user_id: int, service: LinkedInBrowserService, state: SessionState
    ) -> None:
        async with session_scope() as session:
            account = await self._account(session, user_id, create=True)
            account.browser_profile_dir = str(service.browser.profile_dir)
            account.is_connected = state.logged_in
            if state.display_name:
                account.display_name = state.display_name
            if state.logged_in:
                account.last_verified_at = utcnow()
                # If the export fails the persistent profile on disk still holds
                # the session, so this is not worth failing the connection over.
                with suppress(AutomationError):
                    account.encrypted_storage_state = encrypt_json(
                        await service.export_storage_state()
                    )

    @staticmethod
    async def _account(
        session: AsyncSession, user_id: int, *, create: bool = False
    ) -> LinkedInAccount | None:
        account = await session.scalar(
            select(LinkedInAccount).where(LinkedInAccount.user_id == user_id)
        )
        if account is None and create:
            account = LinkedInAccount(user_id=user_id)
            session.add(account)
            await session.flush()
        return account

    # --- Search run -------------------------------------------------------

    async def run_search(
        self, user_id: int, run_id: int, filters: SearchFilters, *, analyze: bool = True
    ) -> None:
        async with self._exclusive(user_id):
            await self._run_search(user_id, run_id, filters, analyze=analyze)

    async def _run_search(
        self, user_id: int, run_id: int, filters: SearchFilters, *, analyze: bool
    ) -> None:
        counters = {"jobs_found": 0, "jobs_analyzed": 0, "jobs_skipped": 0}
        try:
            await self._start_run(run_id)
            await self._publish(
                user_id,
                EventName.AUTOMATION_STARTED,
                run_id=run_id,
                message=f'Searching LinkedIn for "{filters.keywords}".',
                data={"kind": "search", "analyze": analyze},
            )

            service = await self._ready_service(user_id)
            throttle = await self._throttle(user_id)
            checkpoint = await self._checkpoint(run_id)
            processed: set[str] = {str(value) for value in checkpoint.get("processed_ids") or []}
            search_id = await self._run_search_id(run_id)

            await self._check_stop(user_id, run_id)
            postings = await service.search_jobs(filters)
            counters["jobs_found"] = len(postings)
            await self._update_run(run_id, jobs_found=len(postings))

            for index, posting in enumerate(postings, start=1):
                await self._check_stop(user_id, run_id)
                if posting.external_id in processed:
                    continue

                job_id = await self._upsert_job(user_id, search_id, posting)
                await self._publish(
                    user_id,
                    EventName.JOB_FOUND,
                    run_id=run_id,
                    job_id=job_id,
                    message=f"{posting.title} — {posting.company}",
                    data={"external_id": posting.external_id, "url": posting.url},
                )

                if not posting.description:
                    detail = await service.fetch_job_details(posting.external_id)
                    job_id = await self._upsert_job(user_id, search_id, detail)

                if analyze:
                    outcome = await self._analyze_job(user_id, run_id, job_id)
                    if outcome is not None:
                        counters["jobs_analyzed"] += 1
                        if outcome == JobStatus.SKIPPED:
                            counters["jobs_skipped"] += 1

                processed.add(posting.external_id)
                await self._update_run(
                    run_id,
                    checkpoint={
                        "processed_ids": sorted(processed),
                        "page": (index - 1) // PAGE_SIZE,
                    },
                    **counters,
                )
                await self._publish(
                    user_id,
                    EventName.AUTOMATION_PROGRESS,
                    run_id=run_id,
                    job_id=job_id,
                    message=f"Processed {index} of {len(postings)} jobs.",
                    data={"processed": index, "total": len(postings), **counters},
                )
                await throttle.wait_action()

            await self._finish_run(run_id, AutomationRunStatus.COMPLETED, **counters)
            await self._publish(
                user_id,
                EventName.AUTOMATION_STOPPED,
                run_id=run_id,
                level="success",
                message=f"Search finished: {counters['jobs_found']} jobs found.",
                data=dict(counters),
            )
        except StopRequestedError as exc:
            await self._finish_run(run_id, AutomationRunStatus.STOPPED, error=str(exc), **counters)
            await self._publish(
                user_id,
                EventName.AUTOMATION_STOPPED,
                run_id=run_id,
                level="warning",
                message="Search stopped by the user.",
            )
        except SecurityCheckpointError as exc:
            await self._handle_checkpoint(user_id, run_id, exc, **counters)
        except Exception as exc:
            await self._fail_run(user_id, run_id, exc, **counters)
            raise

    async def _run_search_id(self, run_id: int) -> int | None:
        async with session_scope() as session:
            return await session.scalar(
                select(AutomationRun.search_id).where(AutomationRun.id == run_id)
            )

    async def _upsert_job(self, user_id: int, search_id: int | None, posting: JobPosting) -> int:
        """Insert or refresh a job, deduplicating on (user_id, external_id)."""
        async with session_scope() as session:
            job = await session.scalar(
                select(Job).where(Job.user_id == user_id, Job.external_id == posting.external_id)
            )
            if job is None:
                job = Job(
                    user_id=user_id,
                    search_id=search_id,
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
                job.detected_language = _detect_language(posting.description)
            job.workplace_type = posting.workplace_type or job.workplace_type
            job.easy_apply = posting.easy_apply or job.easy_apply
            job.posted_at = posting.posted_at or job.posted_at
            if search_id and job.search_id is None:
                job.search_id = search_id
            if posting.already_applied and job.status != JobStatus.APPLIED:
                job.status = JobStatus.APPLIED
                job.skip_reason = "LinkedIn reports this application was already sent."
            await session.flush()
            return job.id

    async def _analyze_job(self, user_id: int, run_id: int | None, job_id: int) -> JobStatus | None:
        """Score one job with the AI layer. Returns the resulting job status."""
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None or job.user_id != user_id:
                return None
            settings = await self._settings(session, user_id)
            profile = await self._profile_context(session, user_id)
            posting = _posting_from_job(job)
            analysis = await self._ai_analysis(
                session=session,
                user_id=user_id,
                job=job,
                posting=posting,
                profile=profile,
                settings=settings,
            )
            if analysis is None:
                return None

            job.score = analysis.score
            job.score_reasons = list(analysis.reasons)
            job.missing_requirements = list(analysis.missing_requirements)
            if analysis.cover_letter_language:
                job.detected_language = analysis.cover_letter_language
            min_score = int(settings.min_score) if settings else get_settings().default_min_score
            if analysis.refused:
                job.status = JobStatus.ANALYZED
                job.skip_reason = analysis.refusal_reason
            elif analysis.score < min_score or not analysis.recommend_apply:
                job.status = JobStatus.SKIPPED
                job.skip_reason = analysis.summary or (
                    f"Score {analysis.score} is below the {min_score} threshold."
                )
            else:
                job.status = JobStatus.ANALYZED
                job.skip_reason = None
            resulting = job.status
            score = job.score
            title = job.title

        await self._publish(
            user_id,
            EventName.JOB_ANALYZED,
            run_id=run_id,
            job_id=job_id,
            message=f"{title}: score {score}.",
            level="info" if resulting == JobStatus.ANALYZED else "warning",
            data={"score": score, "status": str(resulting)},
        )
        return resulting

    # --- Prepare ----------------------------------------------------------

    async def prepare_application(self, user_id: int, run_id: int, job_id: int) -> int | None:
        async with self._exclusive(user_id):
            return await self._prepare_application(user_id, run_id, job_id)

    async def prepare_applications(
        self, user_id: int, run_id: int, job_ids: Sequence[int]
    ) -> list[int]:
        """Prepare several drafts in one run, stopping cleanly on request."""
        prepared: list[int] = []
        try:
            await self._start_run(run_id)
            await self._publish(
                user_id,
                EventName.AUTOMATION_STARTED,
                run_id=run_id,
                message=f"Preparing {len(job_ids)} application(s) for review.",
                data={"kind": "prepare", "job_ids": list(job_ids)},
            )
            throttle = await self._throttle(user_id)
            checkpoint = await self._checkpoint(run_id)
            # Resuming this run must not touch a job it already handled.
            processed: set[int] = {int(value) for value in checkpoint.get("processed_ids") or []}

            async with self._exclusive(user_id):
                for index, job_id in enumerate(job_ids, start=1):
                    await self._check_stop(user_id, run_id)
                    if job_id in processed:
                        continue
                    try:
                        application_id = await self._prepare_application(user_id, run_id, job_id)
                    except (StopRequestedError, SecurityCheckpointError):
                        raise
                    except AutomationError as exc:
                        logger.warning(
                            "Could not prepare an application.",
                            extra={
                                "action": "engine.prepare",
                                "status": "failed",
                                "user_id": user_id,
                                "job_id": job_id,
                                "error": str(exc),
                            },
                        )
                        continue
                    if application_id is not None:
                        prepared.append(application_id)
                    processed.add(job_id)
                    await self._update_run(
                        run_id,
                        applications_prepared=len(prepared),
                        checkpoint={"processed_ids": sorted(processed)},
                    )
                    await self._publish(
                        user_id,
                        EventName.AUTOMATION_PROGRESS,
                        run_id=run_id,
                        job_id=job_id,
                        application_id=application_id,
                        message=f"Prepared {index} of {len(job_ids)} application(s).",
                        data={"processed": index, "total": len(job_ids)},
                    )
                    await throttle.wait_action()

            await self._finish_run(
                run_id, AutomationRunStatus.COMPLETED, applications_prepared=len(prepared)
            )
            await self._publish(
                user_id,
                EventName.AUTOMATION_STOPPED,
                run_id=run_id,
                level="success",
                message=f"{len(prepared)} application(s) are waiting for your review.",
                data={"applications_prepared": len(prepared)},
            )
        except StopRequestedError as exc:
            await self._finish_run(
                run_id,
                AutomationRunStatus.STOPPED,
                error=str(exc),
                applications_prepared=len(prepared),
            )
            await self._publish(
                user_id,
                EventName.AUTOMATION_STOPPED,
                run_id=run_id,
                level="warning",
                message="Preparation stopped by the user.",
            )
        except SecurityCheckpointError as exc:
            await self._handle_checkpoint(user_id, run_id, exc, applications_prepared=len(prepared))
        except Exception as exc:
            await self._fail_run(user_id, run_id, exc, applications_prepared=len(prepared))
            raise
        return prepared

    async def _prepare_application(
        self, user_id: int, run_id: int | None, job_id: int
    ) -> int | None:
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None or job.user_id != user_id:
                raise AutomationError(f"Job {job_id} does not belong to this user.")
            settings = await self._settings(session, user_id)
            profile = await self._profile_context(session, user_id)
            dry_run = bool(settings.dry_run) if settings else True
            generate_letter = bool(settings.generate_cover_letter) if settings else True
            external_id = job.external_id
            job_title = job.title
            job_company = job.company
            easy_apply = job.easy_apply
            posting = _posting_from_job(job)

            application = await session.scalar(
                select(Application).where(Application.job_id == job_id)
            )
            if application is None:
                application = Application(
                    user_id=user_id, job_id=job_id, status=ApplicationStatus.PREPARING
                )
                session.add(application)
                await session.flush()
            elif application.status in {
                ApplicationStatus.SUBMITTED,
                ApplicationStatus.SUBMITTING,
            }:
                raise AutomationError(
                    f"Application {application.id} was already submitted; nothing to prepare."
                )
            application.status = ApplicationStatus.PREPARING
            application.error_message = None
            application.was_dry_run = dry_run
            application_id = application.id
            resume_filename = profile.resume_path
            cover_letter_existing = application.cover_letter

        await self._publish(
            user_id,
            EventName.APPLICATION_STARTED,
            run_id=run_id,
            job_id=job_id,
            application_id=application_id,
            message=f"Preparing an application for {job_title} at {job_company}.",
            data={"dry_run": dry_run},
        )

        try:
            cover_letter = cover_letter_existing
            if generate_letter and not cover_letter:
                cover_letter = await self._ai_cover_letter(
                    user_id=user_id, posting=posting, profile=profile, settings_row=None
                )

            if dry_run:
                await self._store_draft(
                    user_id=user_id,
                    run_id=run_id,
                    job_id=job_id,
                    application_id=application_id,
                    draft=None,
                    cover_letter=cover_letter,
                    screening=[],
                    resume_filename=resume_filename,
                    dry_run=True,
                )
                return application_id

            if not easy_apply:
                raise EasyApplyUnavailableError(
                    f"Job {external_id} does not offer Easy Apply; apply manually on LinkedIn."
                )

            service = await self._ready_service(user_id)
            questions = await service.open_easy_apply(external_id)
            async with session_scope() as session:
                await self._record(
                    session,
                    user_id=user_id,
                    application_id=application_id,
                    job_id=job_id,
                    run_id=run_id,
                    event_type=ApplicationEventType.FORM_OPENED,
                    message=f"Easy Apply form opened with {len(questions)} field(s).",
                    payload={"fields": [question.label for question in questions]},
                )

            screening = await self._ai_screening(
                user_id=user_id, posting=posting, profile=profile, questions=questions
            )
            answers, enriched = _build_answers(questions, screening, profile)
            draft = await service.fill_and_advance(answers, cover_letter=cover_letter)
            enriched = _merge_draft_answers(enriched, draft)

            await self._store_draft(
                user_id=user_id,
                run_id=run_id,
                job_id=job_id,
                application_id=application_id,
                draft=draft,
                cover_letter=cover_letter,
                screening=enriched,
                resume_filename=resume_filename,
                dry_run=False,
            )
            return application_id

        except StopRequestedError:
            # The kill switch is not a failure; the run records the stop.
            raise
        except Exception as exc:
            await self._fail_application(user_id, run_id, job_id, application_id, exc)
            raise

    async def _store_draft(
        self,
        *,
        user_id: int,
        run_id: int | None,
        job_id: int,
        application_id: int,
        draft: ApplicationDraft | None,
        cover_letter: str | None,
        screening: list[dict[str, Any]],
        resume_filename: str | None,
        dry_run: bool,
    ) -> None:
        """Persist the filled draft and park it in AWAITING_REVIEW."""
        unanswered = [question.label for question in (draft.unanswered if draft else [])]
        low_confidence = [
            entry["question"]
            for entry in screening
            if entry.get("needs_review") or entry.get("confidence") == AnswerConfidence.LOW.value
        ]
        needs_human = bool(unanswered or low_confidence) or (
            draft is not None and not draft.ready_to_submit
        )

        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is None:
                return
            application.cover_letter = cover_letter
            application.screening_answers = screening
            application.resume_filename = (
                Path(resume_filename).name if resume_filename else application.resume_filename
            )
            application.total_steps = draft.total_steps if draft else None
            application.current_step = draft.current_step if draft else None
            application.needs_human_input = needs_human
            application.was_dry_run = dry_run
            application.status = ApplicationStatus.AWAITING_REVIEW

            job = await session.get(Job, job_id)
            if job is not None and job.status not in {JobStatus.APPLIED, JobStatus.SKIPPED}:
                job.status = JobStatus.QUEUED

            message = (
                "Dry run: content generated without opening the LinkedIn form."
                if dry_run
                else "Form filled and stopped at the review step. Waiting for your approval."
            )
            event = await self._record(
                session,
                user_id=user_id,
                application_id=application_id,
                job_id=job_id,
                run_id=run_id,
                event_type=ApplicationEventType.AWAITING_REVIEW,
                message=message,
                payload={
                    "dry_run": dry_run,
                    "unanswered": unanswered,
                    "needs_review": low_confidence,
                    "ready_to_submit": bool(draft.ready_to_submit) if draft else False,
                    "screenshot": draft.screenshot_path if draft else None,
                    "notes": list(draft.notes) if draft else [],
                    "total_steps": draft.total_steps if draft else None,
                    "current_step": draft.current_step if draft else None,
                },
            )
            live = to_live_event(event, job_id=job_id, needs_human_input=needs_human)

        if live is not None:
            await manager.publish(user_id, live)

    async def _fail_application(
        self,
        user_id: int,
        run_id: int | None,
        job_id: int,
        application_id: int,
        exc: Exception,
    ) -> None:
        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is not None:
                application.status = ApplicationStatus.FAILED
                application.error_message = str(exc)
            await self._record(
                session,
                user_id=user_id,
                application_id=application_id,
                job_id=job_id,
                run_id=run_id,
                event_type=ApplicationEventType.ERROR,
                message=str(exc),
                is_error=True,
                payload={"error_type": type(exc).__name__},
            )
        await self._publish(
            user_id,
            EventName.AUTOMATION_ERROR,
            run_id=run_id,
            job_id=job_id,
            application_id=application_id,
            level="error",
            message=str(exc),
            data={"error_type": type(exc).__name__},
        )

    # --- Submit (the only path that sends anything) -----------------------

    async def submit_application(self, user_id: int, application_id: int) -> bool:
        async with self._exclusive(user_id):
            return await self._submit_application(user_id, application_id)

    async def _submit_application(self, user_id: int, application_id: int) -> bool:
        throttle = await self._throttle(user_id)

        async with session_scope() as session:
            application = await session.scalar(
                select(Application)
                .options(selectinload(Application.job))
                .where(Application.id == application_id)
            )
            if application is None or application.user_id != user_id:
                raise AutomationError(f"Application {application_id} does not belong to this user.")
            if application.status != ApplicationStatus.AWAITING_REVIEW:
                raise AutomationError(
                    "Only an application awaiting review can be submitted "
                    # Status columns are plain strings on the way back from the DB.
                    f"(current status: {application.status})."
                )
            if application.approved_at is None:
                raise AutomationError(
                    "This application has not been approved. "
                    "Approve it explicitly before submitting."
                )
            settings = await self._settings(session, user_id)
            if application.was_dry_run or (settings is not None and settings.dry_run):
                raise AutomationError(
                    "Dry run is enabled: nothing is sent to LinkedIn. "
                    "Turn dry run off in settings to submit for real."
                )
            throttle.assert_within_working_hours()
            await throttle.assert_daily_cap(session, user_id)

            application.status = ApplicationStatus.SUBMITTING
            job = application.job
            job_id = job.id
            external_id = job.external_id
            job_title = job.title

        service = self._services.get(user_id)
        if service is None or not service.has_open_draft(external_id):
            exc = AutomationError(
                "The filled Easy Apply form is no longer open in the browser. "
                "Prepare this application again before submitting."
            )
            await self._revert_to_review(user_id, application_id, job_id, exc)
            raise exc

        try:
            confirmed = await service.submit()
        except Exception as exc:
            await self._fail_application(user_id, None, job_id, application_id, exc)
            raise

        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is not None:
                application.status = ApplicationStatus.SUBMITTED
                application.submitted_at = utcnow()
                application.needs_human_input = False
                application.error_message = (
                    None
                    if confirmed
                    else "Submitted, but LinkedIn did not show a confirmation message."
                )
            job = await session.get(Job, job_id)
            if job is not None:
                job.status = JobStatus.APPLIED
            event = await self._record(
                session,
                user_id=user_id,
                application_id=application_id,
                job_id=job_id,
                event_type=ApplicationEventType.SUBMITTED,
                message=f"Application submitted for {job_title}.",
                payload={"confirmed": confirmed},
            )
            live = to_live_event(event, job_id=job_id)

        if live is not None:
            live.level = "success"
            await manager.publish(user_id, live)

        logger.info(
            "Application submitted after explicit user approval.",
            extra={
                "action": "engine.submit",
                "status": "ok",
                "user_id": user_id,
                "application_id": application_id,
                "job_id": job_id,
            },
        )
        # Long, randomized gap before anything else touches LinkedIn.
        await throttle.wait_between_applications()
        return confirmed

    async def _revert_to_review(
        self, user_id: int, application_id: int, job_id: int, exc: Exception
    ) -> None:
        """Undo the SUBMITTING transition when a precondition fails at the browser."""
        async with session_scope() as session:
            application = await session.get(Application, application_id)
            if application is not None:
                application.status = ApplicationStatus.AWAITING_REVIEW
                application.needs_human_input = True
                application.error_message = str(exc)
            await self._record(
                session,
                user_id=user_id,
                application_id=application_id,
                job_id=job_id,
                event_type=ApplicationEventType.ERROR,
                message=str(exc),
                is_error=True,
            )

    async def discard_application(self, user_id: int, application_id: int) -> None:
        """Close the open modal (if any) and mark the application as discarded."""
        async with self._exclusive(user_id):
            service = self._services.get(user_id)
            if service is not None and service.has_open_draft():
                await service.discard()
            async with session_scope() as session:
                application = await session.get(Application, application_id)
                if application is None or application.user_id != user_id:
                    raise AutomationError(
                        f"Application {application_id} does not belong to this user."
                    )
                application.status = ApplicationStatus.DISCARDED
                application.needs_human_input = False
                await self._record(
                    session,
                    user_id=user_id,
                    application_id=application_id,
                    job_id=application.job_id,
                    event_type=ApplicationEventType.DISCARDED,
                    message="Draft discarded by the user.",
                )

    # --- Run bookkeeping --------------------------------------------------

    async def _start_run(self, run_id: int) -> None:
        async with session_scope() as session:
            run = await session.get(AutomationRun, run_id)
            if run is None:
                raise AutomationError(f"Automation run {run_id} does not exist.")
            run.status = AutomationRunStatus.RUNNING
            run.stop_requested = False
            run.error_message = None
            run.blocked_reason = None
            if run.started_at is None:
                run.started_at = utcnow()

    async def _checkpoint(self, run_id: int) -> dict[str, Any]:
        async with session_scope() as session:
            run = await session.get(AutomationRun, run_id)
            return dict(run.checkpoint or {}) if run is not None else {}

    async def _update_run(self, run_id: int, **fields: Any) -> None:
        async with session_scope() as session:
            run = await session.get(AutomationRun, run_id)
            if run is None:
                return
            for key, value in fields.items():
                setattr(run, key, value)

    async def _finish_run(
        self,
        run_id: int,
        status: AutomationRunStatus,
        *,
        error: str | None = None,
        blocked_reason: str | None = None,
        **counters: Any,
    ) -> None:
        async with session_scope() as session:
            run = await session.get(AutomationRun, run_id)
            if run is None:
                return
            run.status = status
            run.finished_at = utcnow()
            run.error_message = error
            run.blocked_reason = blocked_reason
            for key, value in counters.items():
                setattr(run, key, value)

    async def _fail_run(
        self, user_id: int, run_id: int | None, exc: Exception, **counters: Any
    ) -> None:
        logger.exception(
            "Automation run failed.",
            extra={
                "action": "engine.run",
                "status": "failed",
                "user_id": user_id,
                "run_id": run_id,
            },
        )
        if run_id is not None:
            await self._finish_run(run_id, AutomationRunStatus.FAILED, error=str(exc), **counters)
        await self._publish(
            user_id,
            EventName.AUTOMATION_ERROR,
            run_id=run_id,
            level="error",
            message=str(exc),
            data={"error_type": type(exc).__name__},
        )

    async def _handle_checkpoint(
        self,
        user_id: int,
        run_id: int | None,
        exc: SecurityCheckpointError,
        **counters: Any,
    ) -> None:
        """A challenge was detected: stop, mark BLOCKED, and never retry it."""
        logger.error(
            "Security checkpoint detected; the run is blocked.",
            extra={
                "action": "engine.blocked",
                "status": "blocked",
                "user_id": user_id,
                "run_id": run_id,
            },
        )
        if run_id is not None:
            await self._finish_run(
                run_id,
                AutomationRunStatus.BLOCKED,
                error=str(exc),
                blocked_reason=exc.reason,
                **counters,
            )
        await self._publish(
            user_id,
            EventName.AUTOMATION_BLOCKED,
            run_id=run_id,
            level="error",
            message=(
                "LinkedIn showed a security verification. Automation stopped. "
                "Open the browser window and resolve it yourself."
            ),
            data={"reason": exc.reason},
        )
        service = self._services.pop(user_id, None)
        if service is not None:
            try:
                await service.stop()
            except Exception:  # a blocked session must close regardless
                logger.exception(
                    "Could not cleanly close the blocked session.",
                    extra={"action": "engine.blocked", "user_id": user_id},
                )
        await self._publish_session(
            user_id,
            SessionState(blocked=True, blocked_reason=exc.reason),
        )

    # --- Events -----------------------------------------------------------

    async def _publish(
        self,
        user_id: int,
        name: EventName,
        *,
        message: str | None = None,
        level: str = "info",
        run_id: int | None = None,
        job_id: int | None = None,
        application_id: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        await manager.publish(
            user_id,
            make_event(
                name,
                run_id=run_id,
                job_id=job_id,
                application_id=application_id,
                message=message,
                level=level,
                data=data or {},
            ),
        )

    async def _publish_session(self, user_id: int, state: SessionState) -> None:
        await self._publish(
            user_id,
            EventName.SESSION_STATUS,
            message=_session_message(state),
            level="warning" if state.blocked else "info",
            data={
                "browser_open": state.browser_open,
                "logged_in": state.logged_in,
                "blocked": state.blocked,
                "blocked_reason": state.blocked_reason,
                "display_name": state.display_name,
                "current_url": state.current_url,
            },
        )

    @staticmethod
    async def _record(
        session: AsyncSession,
        *,
        user_id: int,
        application_id: int,
        event_type: ApplicationEventType,
        job_id: int | None = None,
        run_id: int | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        is_error: bool = False,
    ) -> Any:
        return await record_event(
            session,
            application_id=application_id,
            event_type=event_type,
            message=message,
            payload=payload,
            run_id=run_id,
            is_error=is_error,
            job_id=job_id,
            user_id=user_id,
        )

    # --- User context -----------------------------------------------------

    @staticmethod
    async def _settings(session: AsyncSession, user_id: int) -> UserSettings | None:
        return await session.scalar(select(UserSettings).where(UserSettings.user_id == user_id))

    async def _throttle(self, user_id: int) -> Throttle:
        async with session_scope() as session:
            return Throttle(await self._settings(session, user_id))

    async def _resume_path(self, user_id: int) -> str | None:
        async with session_scope() as session:
            filename = await session.scalar(
                select(Profile.resume_filename).where(Profile.user_id == user_id)
            )
        if not filename:
            return None
        path = get_settings().resumes_dir / filename
        return str(path) if path.exists() else None

    async def _profile_context(self, session: AsyncSession, user_id: int) -> ProfileContext:
        user = await session.get(User, user_id)
        profile = await session.scalar(select(Profile).where(Profile.user_id == user_id))
        resume_path = await self._resume_path(user_id) if profile else None
        return ProfileContext(
            full_name=user.full_name if user else None,
            email=user.email if user else None,
            headline=profile.headline if profile else None,
            location=profile.location if profile else None,
            phone=profile.phone if profile else None,
            years_of_experience=profile.years_of_experience if profile else None,
            summary=profile.summary if profile else None,
            resume_text=profile.resume_text if profile else None,
            resume_path=resume_path,
            skills=list(profile.skills or []) if profile else [],
            answer_bank=dict(profile.answer_bank or {}) if profile else {},
            preferred_languages=list(profile.preferred_languages or []) if profile else [],
        )

    # --- AI layer calls ---------------------------------------------------

    async def _ai_analysis(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        job: Job,
        posting: JobPosting,
        profile: ProfileContext,
        settings: UserSettings | None,
    ) -> JobAnalysis | None:
        result = await self._call_ai(
            "scoring",
            _SCORING_TARGETS,
            {
                "session": session,
                "user_id": user_id,
                "job": job,
                "job_id": job.id,
                "posting": posting,
                "job_posting": posting,
                "profile": profile,
                "profile_context": profile,
                "settings": settings,
                "user_settings": settings,
            },
        )
        return _as_job_analysis(result)

    async def _ai_cover_letter(
        self,
        *,
        user_id: int,
        posting: JobPosting,
        profile: ProfileContext,
        settings_row: UserSettings | None,
    ) -> str | None:
        async with session_scope() as session:
            settings = settings_row or await self._settings(session, user_id)
            result = await self._call_ai(
                "cover_letter",
                _COVER_LETTER_TARGETS,
                {
                    "session": session,
                    "user_id": user_id,
                    "posting": posting,
                    "job_posting": posting,
                    "profile": profile,
                    "profile_context": profile,
                    "settings": settings,
                    "user_settings": settings,
                    "tone": settings.cover_letter_tone if settings else None,
                    "language": settings.content_language if settings else None,
                },
            )
        return _as_cover_letter(result)

    async def _ai_screening(
        self,
        *,
        user_id: int,
        posting: JobPosting,
        profile: ProfileContext,
        questions: list[FormQuestion],
    ) -> list[ScreeningAnswer]:
        payload_questions = [
            {
                "field_id": question.field_id,
                "question": question.label,
                "label": question.label,
                "type": question.kind,
                "question_type": question.kind,
                "options": list(question.options),
                "required": question.required,
            }
            for question in questions
        ]
        async with session_scope() as session:
            settings = await self._settings(session, user_id)
            result = await self._call_ai(
                "screening",
                _SCREENING_TARGETS,
                {
                    "session": session,
                    "user_id": user_id,
                    "posting": posting,
                    "job_posting": posting,
                    "profile": profile,
                    "profile_context": profile,
                    "settings": settings,
                    "user_settings": settings,
                    "questions": payload_questions,
                    "form_questions": questions,
                },
            )
        return _as_screening_answers(result)

    async def _call_ai(
        self, kind: str, targets: tuple[tuple[str, str], ...], payload: dict[str, Any]
    ) -> Any:
        """Call the AI layer, passing only the arguments it declares.

        The AI module is a separate unit with its own signatures; binding by name
        keeps the engine working whether it takes ORM rows, dataclasses or both,
        and a missing/incompatible AI layer degrades instead of failing the run.
        """
        func = self._resolve_ai(kind, targets)
        if func is None:
            return None
        try:
            signature = inspect.signature(func)
            takes_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            kwargs = (
                dict(payload)
                if takes_kwargs
                else {key: value for key, value in payload.items() if key in signature.parameters}
            )
            result = func(**kwargs)
            if isinstance(result, Awaitable):
                result = await result
            return result
        except Exception as exc:
            logger.warning(
                "The AI layer call failed; continuing without it.",
                extra={"action": f"engine.ai.{kind}", "status": "degraded", "error": str(exc)},
            )
            return None

    def _resolve_ai(self, kind: str, targets: tuple[tuple[str, str], ...]) -> Any:
        if kind in self._ai_cache:
            return self._ai_cache[kind]
        for module_name, attribute in targets:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                continue
            func = getattr(module, attribute, None)
            if callable(func):
                self._ai_cache[kind] = func
                return func
        logger.warning(
            "No AI entry point found; the feature is disabled for this run.",
            extra={"action": f"engine.ai.{kind}", "status": "unavailable"},
        )
        return None


# --- Conversion helpers --------------------------------------------------


def _posting_from_job(job: Job) -> JobPosting:
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


def _as_job_analysis(result: Any) -> JobAnalysis | None:
    if result is None:
        return None
    if isinstance(result, tuple) and result:
        result = result[0]
    if isinstance(result, JobAnalysis):
        return result
    if isinstance(result, dict):
        return JobAnalysis.model_validate(result)
    dumped = getattr(result, "model_dump", None)
    if callable(dumped):
        return JobAnalysis.model_validate(dumped())
    return None


def _as_cover_letter(result: Any) -> str | None:
    if result is None:
        return None
    if isinstance(result, tuple) and result:
        result = result[0]
    if isinstance(result, str):
        return result.strip() or None
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(result, dict):
        value = result.get("content") or result.get("cover_letter")
        return value.strip() if isinstance(value, str) and value.strip() else None
    return None


def _as_screening_answers(result: Any) -> list[ScreeningAnswer]:
    if result is None:
        return []
    if isinstance(result, tuple) and result:
        result = result[0]
    if hasattr(result, "answers"):
        result = result.answers
    if isinstance(result, dict):
        result = result.get("answers", [])
    if not isinstance(result, Iterable):
        return []
    answers: list[ScreeningAnswer] = []
    for item in result:
        if isinstance(item, ScreeningAnswer):
            answers.append(item)
        elif isinstance(item, dict):
            try:
                answers.append(ScreeningAnswer.model_validate(item))
            except Exception:
                continue
    return answers


def _build_answers(
    questions: list[FormQuestion],
    screening: list[ScreeningAnswer],
    profile: ProfileContext,
) -> tuple[list[FormAnswer], list[dict[str, Any]]]:
    """Match AI answers to the real fields, filling the rest from the profile."""
    by_field = {answer.field_id: answer for answer in screening if answer.field_id}
    by_text = {_normalize(answer.question): answer for answer in screening}

    form_answers: list[FormAnswer] = []
    records: list[dict[str, Any]] = []

    for question in questions:
        answer = by_field.get(question.field_id) or by_text.get(_normalize(question.label))
        value = answer.answer.strip() if answer and answer.answer else ""
        confidence = answer.confidence if answer else AnswerConfidence.LOW
        needs_review = answer.needs_review if answer else True
        source = "ai" if value else "none"

        if not value:
            fallback = _answer_from_profile(question, profile)
            if fallback:
                value = fallback
                confidence = AnswerConfidence.MEDIUM
                needs_review = False
                source = "profile"

        if value:
            # `field_id` doubles as the label when the AI could not echo a real id;
            # `EasyApplyModal` falls back to label matching in that case.
            form_answers.append(
                FormAnswer(field_id=question.field_id, value=value, kind=question.kind)
            )
        else:
            needs_review = True

        records.append(
            {
                "field_id": question.field_id,
                "question": question.label,
                "answer": value,
                "type": question.kind,
                "options": list(question.options),
                "required": question.required,
                "confidence": AnswerConfidence(confidence).value,
                "needs_review": bool(needs_review or (question.required and not value)),
                "source": source,
            }
        )

    return form_answers, records


def _merge_draft_answers(
    records: list[dict[str, Any]], draft: ApplicationDraft
) -> list[dict[str, Any]]:
    """Reflect what actually landed in the form back into the stored answers."""
    filled = {answer.field_id for answer in draft.answers}
    unanswered = {question.field_id for question in draft.unanswered}
    known = {record["field_id"] for record in records}

    for record in records:
        record["filled"] = record["field_id"] in filled
        if record["field_id"] in unanswered:
            record["needs_review"] = True

    for question in draft.questions:
        if question.field_id in known:
            continue
        records.append(
            {
                "field_id": question.field_id,
                "question": question.label,
                "answer": question.current_value or "",
                "type": question.kind,
                "options": list(question.options),
                "required": question.required,
                "confidence": AnswerConfidence.LOW.value,
                "needs_review": True,
                "source": "form",
                "filled": question.field_id in filled,
            }
        )
    return records


def _answer_from_profile(question: FormQuestion, profile: ProfileContext) -> str | None:
    """Deterministic answers for the fields we can fill without the AI."""
    label = _normalize(question.label)

    if any(hint in label for hint in _EMAIL_HINTS) and profile.email:
        return profile.email
    if any(hint in label for hint in _PHONE_HINTS) and profile.phone:
        return profile.phone
    if any(hint in label for hint in _FULL_NAME_HINTS) and profile.full_name:
        return profile.full_name
    if any(hint in label for hint in _FIRST_NAME_HINTS) and profile.full_name:
        return profile.full_name.split()[0]
    if any(hint in label for hint in _LAST_NAME_HINTS) and profile.full_name:
        parts = profile.full_name.split()
        return parts[-1] if len(parts) > 1 else None
    if any(hint in label for hint in _LOCATION_HINTS) and profile.location:
        return profile.location
    if any(hint in label for hint in _EXPERIENCE_HINTS) and profile.years_of_experience is not None:
        return str(profile.years_of_experience)

    # Saved answers for recurring screening questions.
    for key, value in profile.answer_bank.items():
        normalized_key = _normalize(str(key).replace("_", " "))
        if not normalized_key or not isinstance(value, (str, int, float)):
            continue
        if normalized_key in label or label in normalized_key:
            return str(value)
    return None


def _session_message(state: SessionState) -> str:
    if state.blocked:
        return "LinkedIn session blocked by a security verification."
    if not state.browser_open:
        return "Browser closed."
    if state.logged_in:
        return "Browser open and signed in to LinkedIn."
    return "Browser open — sign in to LinkedIn in the visible window."


def _normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


# Rough language tag for the AI layer's benefit; the model does the real work.
_PT_MARKERS = (
    " você ",
    " experiência",
    " vaga",
    " conhecimento",
    " desenvolvedor",
    " requisitos",
    " atividades",
    " salário",
)


def _detect_language(text: str) -> str:
    lowered = f" {text.lower()} "
    hits = sum(1 for marker in _PT_MARKERS if marker in lowered)
    return "pt-BR" if hits >= 2 else "en"


_engine: AutomationEngine | None = None


def get_engine() -> AutomationEngine:
    """The process-wide engine instance."""
    global _engine
    if _engine is None:
        _engine = AutomationEngine()
    return _engine
