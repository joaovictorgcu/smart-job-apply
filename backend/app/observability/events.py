"""Nomes canônicos dos eventos e o envelope enviado pelo WebSocket.

Esta é a fonte da verdade compartilhada entre backend e frontend: os tipos aqui
espelham `frontend/src/types/events.ts`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventName(StrEnum):
    """Somente eventos que o painel realmente precisa acompanhar ao vivo."""

    AUTOMATION_STARTED = "automation.started"
    AUTOMATION_PROGRESS = "automation.progress"
    AUTOMATION_STOPPED = "automation.stopped"
    AUTOMATION_ERROR = "automation.error"
    AUTOMATION_BLOCKED = "automation.blocked"  # CAPTCHA / verificação de segurança

    JOB_FOUND = "job.found"
    JOB_ANALYZED = "job.analyzed"

    APPLICATION_STARTED = "application.started"
    APPLICATION_AWAITING_REVIEW = "application.awaiting_review"
    APPLICATION_COMPLETED = "application.completed"

    SESSION_STATUS = "session.status"  # navegador aberto / login do LinkedIn
    LOG = "log"  # linha de log para o feed de atividade


class Event(BaseModel):
    """Envelope de um evento em tempo real."""

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
