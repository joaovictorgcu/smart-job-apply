"""The professional profile the AI and the form filler read from."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.api.deps import CurrentUser, SessionDep
from app.schemas.user import ProfileRead, ProfileUpdate
from app.services import user_service

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
