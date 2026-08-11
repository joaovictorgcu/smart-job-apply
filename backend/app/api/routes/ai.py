"""AI status and on-demand content generation."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.config import get_settings
from app.services import job_service, user_service

router = APIRouter(prefix="/ai", tags=["ai"])


class AIStatus(BaseModel):
    configured: bool
    model: str


class CoverLetterResponse(BaseModel):
    content: str
    language: str


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
