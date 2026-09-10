"""The professional profile the AI and the form filler read from."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile

from app.api.deps import CurrentUser, SessionDep
from app.schemas.intake import IntakeApplied, IntakeApply, ResumeIntakeRead
from app.schemas.resume import ExperienceCreate, ExperienceRead, ExperienceUpdate
from app.schemas.user import ProfileRead, ProfileUpdate
from app.services import intake_service, resume_service, user_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileRead)
async def read_profile(user: CurrentUser, session: SessionDep) -> ProfileRead:
    """Return the profile, creating an empty one on first access."""
    profile = await user_service.get_or_create_profile(session, user)
    return ProfileRead.model_validate(profile)


@router.put("", response_model=ProfileRead)
async def update_profile(
    payload: ProfileUpdate, user: CurrentUser, session: SessionDep
) -> ProfileRead:
    """Update the profile. Only the fields present in the body are touched."""
    profile = await user_service.update_profile(session, user, payload)
    return ProfileRead.model_validate(profile)


@router.get("/experiences", response_model=list[ExperienceRead])
async def list_experiences(user: CurrentUser, session: SessionDep) -> list[ExperienceRead]:
    """The structured half of the master resume: this account's positions, in order."""
    rows = await resume_service.list_experiences(session, user)
    return [ExperienceRead.model_validate(row) for row in rows]


@router.post("/experiences", response_model=ExperienceRead, status_code=201)
async def create_experience(
    payload: ExperienceCreate, user: CurrentUser, session: SessionDep
) -> ExperienceRead:
    """Add one position to the master resume.

    Applications that already hold a derived copy are deliberately left alone —
    theirs is a snapshot of the master as it stood when they were created, and
    rewriting a document a human may have reviewed is not something adding a job
    should do. They simply report themselves as stale.
    """
    row = await resume_service.create_experience(session, user, payload)
    return ExperienceRead.model_validate(row)


@router.patch("/experiences/{experience_id}", response_model=ExperienceRead)
async def update_experience(
    experience_id: int, payload: ExperienceUpdate, user: CurrentUser, session: SessionDep
) -> ExperienceRead:
    """Edit one position on the master resume. Only the fields sent are touched."""
    row = await resume_service.update_experience(session, user, experience_id, payload)
    return ExperienceRead.model_validate(row)


@router.delete("/experiences/{experience_id}", status_code=204)
async def delete_experience(experience_id: int, user: CurrentUser, session: SessionDep) -> Response:
    """Remove a position from the master resume. Existing snapshots keep theirs."""
    await resume_service.delete_experience(session, user, experience_id)
    return Response(status_code=204)


@router.post("/resume", response_model=ProfileRead)
async def upload_resume(
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="Resume as PDF or DOCX, up to 5 MB.")],
) -> ProfileRead:
    """Store the resume file that the Easy Apply form attaches."""
    content = await file.read()
    profile = await user_service.save_resume_file(
        session, user, filename=file.filename or "", content=content
    )
    return ProfileRead.model_validate(profile)


@router.post("/intake", response_model=ResumeIntakeRead)
async def read_resume_intake(
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[
        UploadFile | None, File(description="Resume as PDF or DOCX, up to 5 MB.")
    ] = None,
) -> ResumeIntakeRead:
    """Read a resume and return what it says, for the user to confirm.

    **Nothing about the profile is written here.** With a file, it is stored
    (that PDF is what the application form attaches) and read; with no file, the
    resume text already on the profile is read instead. The response is a
    proposal — including a `warnings` list naming whatever could not be read —
    and `POST /profile/intake/apply` is what persists the user's corrected
    version of it.

    Deterministic and offline: this endpoint behaves the same with no AI key.
    """
    if file is None:
        return await intake_service.read_stored(session, user)
    content = await file.read()
    return await intake_service.read_upload(
        session, user, filename=file.filename or "", content=content
    )


@router.post("/intake/apply", response_model=IntakeApplied)
async def apply_resume_intake(
    payload: IntakeApply, user: CurrentUser, session: SessionDep
) -> IntakeApplied:
    """Save the proposal the user confirmed.

    Only the fields present in the body are written, and positions are appended
    unless `replace_experiences` is set — which removes this account's existing
    positions and is the wizard's explicit "start over".
    """
    return await intake_service.apply(session, user, payload)
