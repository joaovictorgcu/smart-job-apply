"""Auditing: writes an `ApplicationEvent` and emits the matching WS event.

A single entry point for "record this and show it to the user", which keeps the
history in the database and the live feed from ever drifting apart.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationEvent, ApplicationEventType
from app.observability.events import Event, EventName, make_event
from app.observability.logger import get_logger

logger = get_logger(__name__)

# Maps the persisted event to the live event (when the dashboard cares about it).
_LIVE_EVENT: dict[ApplicationEventType, EventName] = {
    ApplicationEventType.JOB_FOUND: EventName.JOB_FOUND,
    ApplicationEventType.JOB_ANALYZED: EventName.JOB_ANALYZED,
    ApplicationEventType.FORM_OPENED: EventName.APPLICATION_STARTED,
    ApplicationEventType.AWAITING_REVIEW: EventName.APPLICATION_AWAITING_REVIEW,
    ApplicationEventType.SUBMITTED: EventName.APPLICATION_COMPLETED,
    ApplicationEventType.ERROR: EventName.AUTOMATION_ERROR,
}


async def record_event(
    session: AsyncSession,
    *,
    application_id: int,
    event_type: ApplicationEventType,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    run_id: int | None = None,
    is_error: bool = False,
    job_id: int | None = None,
    user_id: int | None = None,
) -> ApplicationEvent:
    """Persist one application step and return the created record."""
    event = ApplicationEvent(
        application_id=application_id,
        run_id=run_id,
        event_type=event_type,
        message=message,
        payload=payload or {},
        is_error=is_error,
    )
    session.add(event)
    await session.flush()

    logger.info(
        message or event_type.value,
        extra={
            "action": event_type.value,
            "status": "error" if is_error else "ok",
            "application_id": application_id,
            "job_id": job_id,
            "run_id": run_id,
            "user_id": user_id,
        },
    )
    return event


def to_live_event(
    event: ApplicationEvent, *, job_id: int | None = None, **extra: Any
) -> Event | None:
    """Convert a persisted event into the equivalent WS event, if there is one."""
    name = _LIVE_EVENT.get(event.event_type)
    if name is None:
        return None
    return make_event(
        name,
        run_id=event.run_id,
        job_id=job_id,
        application_id=event.application_id,
        message=event.message,
        level="error" if event.is_error else "info",
        data={**event.payload, **extra},
    )
