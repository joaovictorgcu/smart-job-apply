"""Everything the engine tells the outside world.

Two channels: live dashboard events over the websocket manager, and durable
`ApplicationEvent` rows written inside the caller's session so the audit trail
commits or rolls back with the state change it describes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.contracts import SessionState
from app.automation.engine.base import EngineBase
from app.models import ApplicationEventType
from app.observability import EventName, make_event, record_event
from app.websocket.manager import manager


class EventsMixin(EngineBase):
    """Publishes live events and records the durable application timeline."""

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


def _session_message(state: SessionState) -> str:
    if state.blocked:
        return "LinkedIn session blocked by a security verification."
    if not state.browser_open:
        return "Browser closed."
    if state.logged_in:
        return "Browser open and signed in to LinkedIn."
    return "Browser open — sign in to LinkedIn in the visible window."
