"""Canonical event names and the envelope sent over the WebSocket.

This is the source of truth shared by backend and frontend: the types here mirror
`frontend/src/types/events.ts`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventName(StrEnum):
    """Only the events the dashboard genuinely needs to follow live."""

    AUTOMATION_STARTED = "automation.started"
    AUTOMATION_PROGRESS = "automation.progress"
    AUTOMATION_STOPPED = "automation.stopped"
    AUTOMATION_ERROR = "automation.error"
    AUTOMATION_BLOCKED = "automation.blocked"  # CAPTCHA / security verification

    JOB_FOUND = "job.found"
    JOB_ANALYZED = "job.analyzed"

    APPLICATION_STARTED = "application.started"
    APPLICATION_AWAITING_REVIEW = "application.awaiting_review"
    APPLICATION_COMPLETED = "application.completed"

    SESSION_STATUS = "session.status"  # browser open / LinkedIn login
    LOG = "log"  # log line for the activity feed


class Event(BaseModel):
    """Envelope of a real-time event."""

    name: EventName
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: int | None = None
    job_id: int | None = None
    application_id: int | None = None
    message: str | None = None
    level: str = "info"  # info | warning | error | success
    data: dict[str, Any] = Field(default_factory=dict)


def make_event(name: EventName, **kwargs: Any) -> Event:
    return Event(name=name, **kwargs)
