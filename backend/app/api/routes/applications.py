"""Applications: review, edit, approve or discard. Submitting is opt-in per item."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import CurrentUser, LimitDep, OffsetDep, SessionDep
from app.models import ApplicationStatus
from app.schemas.application import (
    ApplicationDetail,
    ApplicationEventOut,
    ApplicationRead,
    ApplicationUpdate,
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


@router.get("/{application_id}", response_model=ApplicationDetail)
async def read_application(
    application_id: int, user: CurrentUser, session: SessionDep
) -> ApplicationDetail:
    """Return the draft with its job and its full event trail."""
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
