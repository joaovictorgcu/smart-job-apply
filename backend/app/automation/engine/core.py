"""Engine assembly, concurrency and the kill switch.

`AutomationEngine` is composed here from one mixin per phase of a run. This
module owns what every phase depends on: the per-user browser service, the
per-user lock and the global semaphore that serialize browser work, the
background-task registry behind `launch_background`, and the cooperative stop
flag that lets a running loop be interrupted between steps.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.ai.port import AIOrchestrator, get_orchestrator
from app.automation.engine.context import ContextMixin
from app.automation.engine.events import EventsMixin
from app.automation.engine.prepare import PrepareMixin
from app.automation.engine.runs import RunsMixin
from app.automation.engine.search import SearchMixin
from app.automation.engine.session import SessionMixin
from app.automation.engine.submit import SubmitMixin
from app.automation.errors import AutomationError, StopRequestedError
from app.config import get_settings
from app.database.session import session_scope
from app.models import AutomationRun, AutomationRunStatus
from app.observability import EventName, get_logger

if TYPE_CHECKING:
    from app.automation.linkedin.service import LinkedInBrowserService

logger = get_logger(__name__)


class AutomationEngine(
    SessionMixin,
    SearchMixin,
    PrepareMixin,
    SubmitMixin,
    RunsMixin,
    EventsMixin,
    ContextMixin,
):
    """One instance per process; use `get_engine()`."""

    def __init__(self, *, ai: AIOrchestrator | None = None) -> None:
        settings = get_settings()
        self._semaphore = asyncio.Semaphore(max(1, settings.max_concurrent_sessions))
        self._services: dict[int, LinkedInBrowserService] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._tasks: dict[int, asyncio.Task[Any]] = {}
        self._detached: set[asyncio.Task[Any]] = set()
        self._stop_requested: set[int] = set()
        self._ai = ai or get_orchestrator()

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
