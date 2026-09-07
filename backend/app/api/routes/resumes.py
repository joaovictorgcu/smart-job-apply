"""The master resume, and the copy each application carries.

Read as one flow: `/resumes/master` is the single source of truth the user edits,
`/resumes/applications/{id}` is what one application actually presents, and
`/resumes/versions` is every copy that exists — which is how the user sees that
the versions are per-vacancy and independent without a versioning screen.

Nothing here calls a model or reaches the network. The derivation is
deterministic (`app.domain.resume`), so these endpoints behave identically on a
deployment with no Anthropic key.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.resume import (
    ApplicationResumeRead,
    ApplicationResumeUpdate,
    MasterResumeRead,
    ResumeVersionSummary,
)
from app.services import resume_service

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.get("/master", response_model=MasterResumeRead)
async def read_master_resume(user: CurrentUser, session: SessionDep) -> MasterResumeRead:
    """The master resume: the profile's text and skills plus the structured positions.

    Its `fingerprint` is what every application snapshot is compared against to
    decide whether it has gone stale.
    """
    return await resume_service.read_master(session, user)


@router.get("/versions", response_model=list[ResumeVersionSummary])
async def list_resume_versions(
    user: CurrentUser, session: SessionDep
) -> list[ResumeVersionSummary]:
    """Every application-specific version this account holds, newest first.

    Metadata only — the posting it was adapted to, its adherence and whether it
    was hand-edited. Reading a version means opening its application.
    """
    return await resume_service.list_versions(session, user)


@router.get("/applications/{application_id}", response_model=ApplicationResumeRead)
async def read_application_resume(
    application_id: int, user: CurrentUser, session: SessionDep
) -> ApplicationResumeRead:
    """The resume this application presents, or 404 if none was derived yet.

    A 404 is a normal state, not a failure: applications created before this
    existed have no honest snapshot, and the review screen offers the action.
    """
    return await resume_service.read_for_application(session, user, application_id)


@router.post("/applications/{application_id}", response_model=ApplicationResumeRead)
async def adapt_application_resume(
    application_id: int, user: CurrentUser, session: SessionDep
) -> ApplicationResumeRead:
    """Adapt the master resume to this application's posting — or adapt it again.

    Replaces this application's copy and bumps its version. **No other
    application's copy and no part of the master resume is touched**, which is
    what makes "adapt again" safe to press. Any hand edits to *this* copy are
    replaced, which is the point of asking for a fresh derivation.
    """
    await resume_service.adapt_application_resume(session, user, application_id)
    return await resume_service.read_for_application(session, user, application_id)


@router.patch("/applications/{application_id}", response_model=ApplicationResumeRead)
async def update_application_resume(
    application_id: int,
    payload: ApplicationResumeUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> ApplicationResumeRead:
    """Edit this application's copy, and only this one.

    The master resume is a different table and every sibling application is a
    different row, so there is no write path from here to either.
    """
    await resume_service.update_application_resume(session, user, application_id, payload)
    return await resume_service.read_for_application(session, user, application_id)
