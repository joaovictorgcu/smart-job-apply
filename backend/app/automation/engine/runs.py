"""`AutomationRun` bookkeeping: start, progress, finish, fail, blocked.

Every write happens in its own short session so a crashed or stopped run leaves
the last committed checkpoint behind and can be resumed from it. A security
challenge is the terminal case: it ends the run, closes the session, and is
never retried.
"""

from __future__ import annotations

from typing import Any

from app.automation.contracts import SessionState
from app.automation.engine.base import EngineBase
from app.automation.errors import AutomationError, SecurityCheckpointError
from app.database.base import utcnow
from app.database.session import session_scope
from app.models import AutomationRun, AutomationRunStatus
from app.observability import EventName, get_logger

logger = get_logger(__name__)


class RunsMixin(EngineBase):
    """Owns the lifecycle of the `AutomationRun` row behind a search or prepare."""

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
