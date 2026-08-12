"""Applications: review, edit, approve or discard. Submitting is opt-in per item."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Response

from app.api.deps import CurrentUser, LimitDep, OffsetDep, SessionDep
from app.models import ApplicationStatus
from app.schemas.application import (
    ApplicationCard,
    ApplicationDetail,
    ApplicationEventOut,
    ApplicationRead,
    ApplicationUpdate,
    OutcomeUpdate,
)
from app.schemas.automation import SubmitRequest
from app.schemas.common import Page
from app.services import application_service, automation_service

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=Page[ApplicationRead])
async def list_applications(
    user: CurrentUser,
    session: SessionDep,
    status: Annotated[ApplicationStatus | None, Query(description="Filter by status.")] = None,
    limit: LimitDep = 50,
    offset: OffsetDep = 0,
) -> Page[ApplicationRead]:
    """List applications, most recently touched first."""
    applications, total = await application_service.list_applications(
        session, user, status=status, limit=limit, offset=offset
    )
    return Page[ApplicationRead](
        items=[application_service.to_application_read(item) for item in applications],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/board", response_model=list[ApplicationCard])
async def read_board(user: CurrentUser, session: SessionDep) -> list[ApplicationCard]:
    """Submitted applications for the pipeline board.

    Returned flat, most recently moved first; the dashboard groups them into
    outcome columns (Applied / Interview / Offer / Rejected / Ghosted).
    """
    applications = await application_service.list_board(session, user)
    return [application_service.to_application_card(item) for item in applications]


@router.get("/export")
async def export_applications(user: CurrentUser, session: SessionDep) -> Response:
    """The full application history as a CSV download.

    Registered before the dynamic route so "export" is never captured as an id.
    """
    content = await application_service.export_csv(session, user)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="applications.csv"'},
    )


@router.get("/{application_id}", response_model=ApplicationDetail)
async def read_application(
    application_id: int, user: CurrentUser, session: SessionDep
) -> ApplicationDetail:
    """Return the draft with its job and its full event trail."""
    application = await application_service.get_application(session, user, application_id)
    return application_service.to_application_detail(application)


@router.patch("/{application_id}/outcome", response_model=ApplicationDetail)
async def set_application_outcome(
    application_id: int,
    payload: OutcomeUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> ApplicationDetail:
    """Record what happened after applying (interview, offer, rejection, no reply).

    Only a submitted application can be moved; this never submits anything.
    """
    await application_service.set_outcome(
        session, user, application_id, payload.outcome, note=payload.note
    )
    application = await application_service.get_application(session, user, application_id)
    return application_service.to_application_detail(application)


@router.patch("/{application_id}", response_model=ApplicationDetail)
async def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> ApplicationDetail:
    """Edit the cover letter and the screening answers before approving.

    Allowed only while the application is a draft or awaiting review. Editing does
    not approve or submit anything; `needs_human_input` is recomputed from the
    answers that are still flagged for review.
    """
    await application_service.update_draft(session, user, application_id, payload)
    application = await application_service.get_application(session, user, application_id)
    return application_service.to_application_detail(application)


@router.post("/{application_id}/submit", response_model=ApplicationDetail)
async def submit_application(
    application_id: int,
    payload: SubmitRequest,
    user: CurrentUser,
    session: SessionDep,
    background: BackgroundTasks,
) -> ApplicationDetail:
    """Approve and submit this one application. **This is the only submitting path.**

    Requires `confirm: true`, an application that is awaiting review, dry-run turned
    off in settings and room under the daily cap. The approval is recorded in the
    event trail and the actual click happens in a tracked automation run.
    """
    await automation_service.submit_application(
        session, user, application_id, payload, background=background
    )
    application = await application_service.get_application(session, user, application_id)
    return application_service.to_application_detail(application)


@router.post("/{application_id}/discard", response_model=ApplicationDetail)
async def discard_application(
    application_id: int, user: CurrentUser, session: SessionDep
) -> ApplicationDetail:
    """Throw the draft away. A submitted application cannot be discarded."""
    await application_service.discard(session, user, application_id)
    application = await application_service.get_application(session, user, application_id)
    return application_service.to_application_detail(application)


@router.get("/{application_id}/events", response_model=list[ApplicationEventOut])
async def list_application_events(
    application_id: int, user: CurrentUser, session: SessionDep
) -> list[ApplicationEventOut]:
    """Every recorded step of this application, oldest first."""
    events = await application_service.list_events(session, user, application_id)
    return [ApplicationEventOut.model_validate(event) for event in events]
