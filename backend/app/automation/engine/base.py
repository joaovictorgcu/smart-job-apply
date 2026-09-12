"""The cross-module surface the engine mixins share.

`AutomationEngine` is assembled from one mixin per phase of a run, and those
phases call into each other: the search loop publishes events, the prepare loop
asks the session mixin for a ready browser, both write run bookkeeping. This
module declares that surface once, so a type checker can follow a call from the
mixin that makes it to the mixin that implements it.

Nothing here exists at runtime. The state attributes are created by
`AutomationEngine.__init__` and every method below is implemented by exactly one
mixin, so `EngineBase` contributes an empty class body to the MRO.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ai.port import AIOrchestrator
    from app.automation.contracts import ProfileContext, SessionState
    from app.automation.errors import SecurityCheckpointError
    from app.automation.linkedin.service import LinkedInBrowserService
    from app.automation.throttle import Throttle
    from app.models import ApplicationEventType, AutomationRunStatus, UserSettings
    from app.observability import EventName


class EngineBase:
    """Declaration-only base: the state and the internal API every mixin sees."""

    # Created in `AutomationEngine.__init__` (core.py).
    _semaphore: asyncio.Semaphore
    _services: dict[int, LinkedInBrowserService]
    _locks: dict[int, asyncio.Lock]
    _tasks: dict[int, asyncio.Task[Any]]
    _detached: set[asyncio.Task[Any]]
    _stop_requested: set[int]
    _ai: AIOrchestrator

    if TYPE_CHECKING:
        # --- core.py ---

        def _exclusive(self, user_id: int) -> AbstractAsyncContextManager[None]: ...

        async def _check_stop(self, user_id: int, run_id: int | None) -> None: ...

        # --- session.py ---

        async def _ready_service(self, user_id: int) -> LinkedInBrowserService: ...

        # --- prepare.py ---

        async def _fail_application(
            self,
            user_id: int,
            run_id: int | None,
            job_id: int,
            application_id: int,
            exc: Exception,
        ) -> None: ...

        # --- runs.py ---

        async def _start_run(self, run_id: int) -> None: ...

        async def _checkpoint(self, run_id: int) -> dict[str, Any]: ...

        async def _update_run(self, run_id: int, **fields: Any) -> None: ...

        async def _finish_run(
            self,
            run_id: int,
            status: AutomationRunStatus,
            *,
            error: str | None = None,
            blocked_reason: str | None = None,
            **counters: Any,
        ) -> None: ...

        async def _fail_run(
            self, user_id: int, run_id: int | None, exc: Exception, **counters: Any
        ) -> None: ...

        async def _handle_checkpoint(
            self,
            user_id: int,
            run_id: int | None,
            exc: SecurityCheckpointError,
            **counters: Any,
        ) -> None: ...

        # --- events.py ---

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
        ) -> None: ...

        async def _publish_session(self, user_id: int, state: SessionState) -> None: ...

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
        ) -> Any: ...

        # --- context.py ---

        @staticmethod
        async def _settings(session: AsyncSession, user_id: int) -> UserSettings | None: ...

        async def _throttle(self, user_id: int) -> Throttle: ...

        async def _resume_path(self, user_id: int) -> str | None: ...

        async def _application_resume_path(
            self, user_id: int, application_id: int
        ) -> str | None: ...

        async def _profile_context(self, session: AsyncSession, user_id: int) -> ProfileContext: ...
