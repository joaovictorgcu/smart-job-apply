"""AI status and on-demand content generation."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.ai import scoring
from app.ai.schemas import DraftReview
from app.api.deps import CurrentUser, SessionDep
from app.api.errors import NotFoundError, UpstreamError
from app.config import get_settings
from app.schemas.tailoring import TailoredResumeRead, TailoredResumeUpdate
from app.services import application_service, job_service, tailoring_service, user_service

router = APIRouter(prefix="/ai", tags=["ai"])


class AIStatus(BaseModel):
    configured: bool
    model: str


class CoverLetterResponse(BaseModel):
    content: str
    language: str


class InterviewPrepResponse(BaseModel):
    content: str


@router.get("/status", response_model=AIStatus)
async def read_status(user: CurrentUser, session: SessionDep) -> AIStatus:
    """Whether an API key is configured, and which model this account would use."""
    settings = get_settings()
    user_settings = await user_service.get_or_create_settings(session, user)
    return AIStatus(
        configured=settings.ai_enabled,
        model=user_settings.ai_model or settings.anthropic_model,
    )


@router.post("/cover-letter/{job_id}", response_model=CoverLetterResponse)
async def create_cover_letter(
    job_id: int, user: CurrentUser, session: SessionDep
) -> CoverLetterResponse:
    """Draft a cover letter for one job, in the tone and language from settings.

    The text is returned for review, not stored on the application: attach it with
    `PATCH /api/applications/{id}` once you are happy with it.
    """
    letter = await job_service.generate_cover_letter(session, user, job_id)
    return CoverLetterResponse(content=letter.content, language=letter.language)


@router.post("/tailor-cv/{job_id}", response_model=TailoredResumeRead)
async def create_tailored_cv(
    job_id: int, user: CurrentUser, session: SessionDep
) -> TailoredResumeRead:
    """Adapt the user's resume to one job — reorganized and re-emphasized, never invented.

    Overwrites any previous draft for this job. The response carries the change
    list, requirements the resume cannot back, and the invention guard's flags.
    """
    row = await tailoring_service.create_tailored_resume(session, user, job_id)
    current = await tailoring_service.current_fingerprint(session, user)
    return tailoring_service.to_read(row, current=current)


@router.post("/review/{application_id}", response_model=DraftReview)
async def review_application_draft(
    application_id: int, user: CurrentUser, session: SessionDep
) -> DraftReview:
    """Second-pass AI review of a drafted application, from a fresh context.

    Returns suggested letter edits, a four-category critique, and a requirement
    coverage table. Nothing is applied automatically and nothing is submitted —
    the user decides what to change on the review screen.
    """
    application = await application_service.get_application(session, user, application_id)
    settings_row = await user_service.get_or_create_settings(session, user)
    profile_ctx = await user_service.build_profile_context(session, user)
    result = await scoring.review_draft(
        session,
        user=user,
        job=application.job,
        application=application,
        profile_ctx=profile_ctx,
        settings_row=settings_row,
    )
    if result is None:
        raise UpstreamError("The AI did not return a review. Try again, or review by hand.")
    return result


@router.post("/interview-prep/{application_id}", response_model=InterviewPrepResponse)
async def create_interview_prep(
    application_id: int, user: CurrentUser, session: SessionDep
) -> InterviewPrepResponse:
    """A markdown prep pack for an interview, grounded only in stored data.

    Uses the frozen submission snapshot (the posting and the exact materials
    sent), the fit analysis gaps, and the profile — no web research, nothing
    invented.
    """
    application = await application_service.get_application(session, user, application_id)
    settings_row = await user_service.get_or_create_settings(session, user)
    profile_ctx = await user_service.build_profile_context(session, user)
    content = await scoring.prepare_interview(
        session,
        user=user,
        job=application.job,
        application=application,
        profile_ctx=profile_ctx,
        settings_row=settings_row,
    )
    if content is None:
        raise UpstreamError("The AI did not return a prep pack. Try again.")
    return InterviewPrepResponse(content=content)


@router.get("/tailor-cv/{job_id}", response_model=TailoredResumeRead)
async def read_tailored_cv(
    job_id: int, user: CurrentUser, session: SessionDep
) -> TailoredResumeRead:
    """The stored tailored resume for one job, or 404 if none has been generated."""
    row = await tailoring_service.get_tailored_resume(session, user, job_id)
    if row is None:
        raise NotFoundError("No tailored resume for this job yet.")
    current = await tailoring_service.current_fingerprint(session, user)
    return tailoring_service.to_read(row, current=current)


@router.patch("/tailor-cv/{job_id}", response_model=TailoredResumeRead)
async def update_tailored_cv(
    job_id: int, payload: TailoredResumeUpdate, user: CurrentUser, session: SessionDep
) -> TailoredResumeRead:
    """Save the user's edits to the tailored resume and re-check it for invention."""
    row = await tailoring_service.update_tailored_resume(session, user, job_id, payload.content)
    current = await tailoring_service.current_fingerprint(session, user)
    return tailoring_service.to_read(row, current=current)
