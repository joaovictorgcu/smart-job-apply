"""CV tailoring: generate a job-specific resume, guard it, store it, edit it.

The AI layer adapts the resume; this layer owns the safety net. Every generated or
edited draft is run through the invention guard (`flag_unsupported_skills`) so a
fabricated technology is surfaced to the user even if the model ignored the rule.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import flag_unsupported_skills
from app.api.errors import NotFoundError, PreconditionFailedError, UpstreamError
from app.automation.contracts import ProfileContext
from app.config import get_settings
from app.models import TailoredResume, User
from app.observability import get_logger
from app.schemas.tailoring import CVChangeOut, TailoredResumeRead
from app.services import job_service, user_service

logger = get_logger(__name__)


def _source_text(profile: ProfileContext) -> str:
    """Everything the candidate actually provided, for the invention guard.

    Skills and the headline are included so a skill the user genuinely lists is
    never flagged just because it is absent from the free-text resume body.
    """
    parts = [
        profile.resume_text or "",
        profile.summary or "",
        profile.headline or "",
        " ".join(profile.skills or []),
    ]
    return "\n".join(part for part in parts if part.strip())


def _fingerprint(profile: ProfileContext) -> str:
    return hashlib.sha256(_source_text(profile).encode("utf-8")).hexdigest()


async def current_fingerprint(session: AsyncSession, user: User) -> str:
    """Fingerprint of the user's profile as it stands now (for staleness checks)."""
    return _fingerprint(await user_service.build_profile_context(session, user))


async def get_tailored_resume(
    session: AsyncSession, user: User, job_id: int
) -> TailoredResume | None:
    """The stored draft for one job, or None. Scoped to the user for isolation."""
    result = await session.execute(
        select(TailoredResume).where(
            TailoredResume.user_id == user.id, TailoredResume.job_id == job_id
        )
    )
    return result.scalar_one_or_none()


async def create_tailored_resume(session: AsyncSession, user: User, job_id: int) -> TailoredResume:
    """Generate (or regenerate) a tailored resume for one job.

    Raises `PreconditionFailedError` when there is nothing to tailor (no job
    description, or no resume text on the profile) and `UpstreamError` when the AI
    returns nothing usable.
    """
    from app.ai import tailor_resume as ai_tailor_resume

    job = await job_service.get_job(session, user, job_id)
    if not job.description:
        raise PreconditionFailedError(
            "This job has no description yet. Run a search with analysis enabled first."
        )

    profile = await user_service.build_profile_context(session, user)
    if not (profile.resume_text or "").strip():
        raise PreconditionFailedError(
            "Add your resume text in Profile before tailoring — there is nothing to adapt yet."
        )
    settings_row = await user_service.get_or_create_settings(session, user)

    result = await ai_tailor_resume(
        session, user=user, job=job, profile_ctx=profile, settings_row=settings_row
    )
    if result is None:
        raise UpstreamError(
            "The AI did not return a tailored resume. Try again, or edit your resume by hand."
        )

    flags = flag_unsupported_skills(_source_text(profile), result.tailored_markdown)
    row = await get_tailored_resume(session, user, job_id)
    if row is None:
        row = TailoredResume(user_id=user.id, job_id=job.id)
        session.add(row)

    row.content = result.tailored_markdown
    row.changes = [change.model_dump(mode="json") for change in result.changes]
    row.unsupported_requirements = list(result.unsupported_requirements)
    row.invention_flags = flags
    row.summary = result.summary
    row.model = settings_row.ai_model or get_settings().anthropic_model
    row.source_fingerprint = _fingerprint(profile)
    row.was_edited = False
    await session.flush()

    logger.info(
        "Tailored resume generated.",
        extra={
            "action": "cv.tailor",
            "status": "ok",
            "user_id": user.id,
            "job_id": job.id,
            "invention_flags": len(flags),
            "unsupported": len(row.unsupported_requirements),
        },
    )
    return row


async def update_tailored_resume(
    session: AsyncSession, user: User, job_id: int, content: str
) -> TailoredResume:
    """Save the user's edits and re-run the invention guard on the edited text."""
    row = await get_tailored_resume(session, user, job_id)
    if row is None:
        raise NotFoundError("No tailored resume for this job yet. Generate one first.")

    profile = await user_service.build_profile_context(session, user)
    row.content = content
    row.was_edited = True
    # Re-guard the edited text: the user can introduce a claim too.
    row.invention_flags = flag_unsupported_skills(_source_text(profile), content)
    await session.flush()

    logger.info(
        "Tailored resume edited.",
        extra={
            "action": "cv.tailor.edit",
            "status": "ok",
            "user_id": user.id,
            "job_id": job_id,
            "invention_flags": len(row.invention_flags),
        },
    )
    return row


def to_read(row: TailoredResume, *, current: str | None) -> TailoredResumeRead:
    """Build the response, computing staleness against the current profile."""
    stale = bool(row.source_fingerprint and current and row.source_fingerprint != current)
    changes = [
        CVChangeOut(
            section=str(change.get("section", "")),
            action=str(change.get("action", "")),
            detail=str(change.get("detail", "")),
        )
        for change in (row.changes or [])
    ]
    return TailoredResumeRead(
        job_id=row.job_id,
        content=row.content,
        changes=changes,
        unsupported_requirements=list(row.unsupported_requirements or []),
        invention_flags=list(row.invention_flags or []),
        summary=row.summary,
        model=row.model,
        was_edited=row.was_edited,
        is_stale=stale,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
