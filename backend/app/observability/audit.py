"""Auditing: writes an `ApplicationEvent` and emits the matching WS event.

A single entry point for "record this and show it to the user", which keeps the
history in the database and the live feed from ever drifting apart.

`record_audit_event` is the account-level counterpart: it records the changes to
the guardrails themselves, which no application event would ever cover.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationEvent, ApplicationEventType, AuditAction, AuditEvent
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


# Which way each guardrail has to move to allow *more* automation: "off" for a
# switch being turned off, "up"/"down" for a threshold. Shorter delays and a wider
# working-hour window both mean more unattended activity, which is why lowering
# `working_hour_start` and raising `working_hour_end` are equally relaxations.
GUARDRAILS: dict[str, str] = {
    "dry_run": "off",
    "require_manual_approval": "off",
    "daily_cap": "up",
    "min_score": "down",
    "action_delay_min": "down",
    "action_delay_max": "down",
    "apply_delay_min": "down",
    "apply_delay_max": "down",
    "working_hour_start": "down",
    "working_hour_end": "up",
}


def relaxations(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Name the guardrails that were loosened, in `GUARDRAILS` order.

    Only fields present on both sides are judged: a field the caller did not
    include is not a change, and a `None` on either side is not comparable.
    """
    relaxed: list[str] = []
    for field, direction in GUARDRAILS.items():
        if field not in before or field not in after:
            continue
        old, new = before[field], after[field]
        if old is None or new is None or old == new:
            continue
        if direction == "off":
            loosened = bool(old) and not bool(new)
        elif direction == "up":
            loosened = new > old
        else:
            loosened = new < old
        if loosened:
            relaxed.append(field)
    return relaxed


async def record_audit_event(
    session: AsyncSession,
    *,
    user_id: int,
    action: AuditAction,
    subject_type: str,
    subject_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    """Persist one account-level change and return the created record."""
    old = before or {}
    new = after or {}
    relaxed = relaxations(old, new)

    event = AuditEvent(
        user_id=user_id,
        subject_type=subject_type,
        subject_id=subject_id,
        action=action,
        before=old,
        after=new,
        relaxed=relaxed,
    )
    session.add(event)
    await session.flush()

    # A loosened guardrail is the one change worth waking someone up for, so it
    # leaves a WARNING even though the request itself succeeded.
    log = logger.warning if relaxed else logger.info
    log(
        "Guardrail relaxed." if relaxed else "Change recorded.",
        extra={
            "action": "audit.relaxed" if relaxed else "audit.record",
            "status": "ok",
            "user_id": user_id,
            "audit_action": action.value,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "fields": sorted(new),
            "relaxed": relaxed,
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
