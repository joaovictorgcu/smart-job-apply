"""Driving the browser: session, search, preview, prepare and the kill switch."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import CurrentUser, SessionDep
from app.schemas.automation import (
    AutomationRunRead,
    PrepareRequest,
    PreviewResponse,
    SearchRunRequest,
)
from app.schemas.common import Message
from app.schemas.user import SessionStatus
from app.services import automation_service

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/session", response_model=SessionStatus)
async def read_session(user: CurrentUser, session: SessionDep) -> SessionStatus:
    """Browser and LinkedIn login state, plus today's counters and guardrails."""
    return await automation_service.session_status(session, user)


@router.post("/session/start", response_model=SessionStatus)
async def start_session(user: CurrentUser, session: SessionDep) -> SessionStatus:
    """Open the browser window and return immediately.

    The user logs in themselves in that window: the application never asks for,
    receives or stores a LinkedIn password. Poll this endpoint (or watch the
    `session.status` WebSocket event) until `logged_in` turns true.
    """
    return await automation_service.start_session(session, user)


@router.post("/session/stop", response_model=SessionStatus)
async def stop_session(user: CurrentUser, session: SessionDep) -> SessionStatus:
    """Close the browser window, persisting the session cookies encrypted."""
    return await automation_service.stop_session(session, user)


@router.post("/search", response_model=AutomationRunRead)
async def run_search(
    payload: SearchRunRequest,
    user: CurrentUser,
    session: SessionDep,
    background: BackgroundTasks,
) -> AutomationRunRead:
    """Start a search run in the background and return its record.

    Searching and scoring never open the application form and never submit
    anything. Follow the progress through the WebSocket feed or `/automation/runs`.
    """
    run = await automation_service.start_search_run(session, user, payload, background=background)
    return automation_service.to_run_read(run)


@router.post("/preview", response_model=PreviewResponse)
async def preview(
    payload: PrepareRequest, user: CurrentUser, session: SessionDep
) -> PreviewResponse:
    """Describe what preparing these jobs would do — without doing anything.

    Shows how many jobs would be processed, how many are already applied to or
    below the score threshold, the remaining daily quota and any warnings. The
    frontend must show this before asking for confirmation.
    """
    return await automation_service.build_preview(session, user, payload.job_ids)


@router.post("/prepare", response_model=AutomationRunRead)
async def prepare(
    payload: PrepareRequest,
    user: CurrentUser,
    session: SessionDep,
    background: BackgroundTasks,
) -> AutomationRunRead:
    """Fill the Easy Apply forms and stop at review. Requires `confirmed: true`.

    Every prepared application lands in `awaiting_review`; submitting is a separate,
    per-application confirmation (`POST /api/applications/{id}/submit`).
    """
    run = await automation_service.start_prepare_run(session, user, payload, background=background)
    return automation_service.to_run_read(run)


@router.post("/stop", response_model=Message)
async def stop(user: CurrentUser, session: SessionDep) -> Message:
    """Kill switch: tell the engine to stand down at its next step.

    Responds immediately. The stop is cooperative, so an application that is being
    filled is left as it is rather than half-submitted; the browser window stays
    open so you can see where it stopped.
    """
    flagged = await automation_service.stop_all(session, user)
    return Message(detail=f"Stop requested. {flagged} active run(s) affected.")


@router.get("/runs", response_model=list[AutomationRunRead])
async def list_runs(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AutomationRunRead]:
    """Recent automation runs, newest first."""
    runs = await automation_service.list_runs(session, user, limit=limit)
    return [automation_service.to_run_read(run) for run in runs]


@router.get("/runs/{run_id}", response_model=AutomationRunRead)
async def read_run(run_id: int, user: CurrentUser, session: SessionDep) -> AutomationRunRead:
    """Return one run with its counters and stop/blocked flags."""
    run = await automation_service.get_run(session, user, run_id)
    return automation_service.to_run_read(run)
