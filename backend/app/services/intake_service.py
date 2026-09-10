"""Turning an uploaded resume into a profile the user only has to correct.

The onboarding promise is "upload your CV, check what we found". Two steps, and
keeping them apart is deliberate:

`read_upload` / `read_stored` produce a **proposal** and write nothing about the
candidate. (An upload does store the file itself, because that PDF is what the
Easy Apply form attaches and asking for it twice would be silly — but not one
field of the profile moves.)

`apply` writes, and only what the user sent back. That is where a parser's
mistake stops being cheap, so it is the step behind an explicit confirmation.

The parsing itself lives in `app.domain.resume_intake`: pure, offline and
provable against plain text, for the same reason the per-posting derivation is.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ValidationError
from app.domain import resume_intake
from app.models import Experience, Profile, User
from app.observability import get_logger
from app.schemas.intake import (
    IntakeApplied,
    IntakeApply,
    IntakeEducationRead,
    IntakeExperienceRead,
    IntakeProjectRead,
    ResumeIntakeRead,
)
from app.schemas.user import ProfileRead, ProfileUpdate
from app.services import resume_service, user_service

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _Source:
    text: str
    filename: str | None


def _to_read(intake: resume_intake.ResumeIntake, source: _Source) -> ResumeIntakeRead:
    return ResumeIntakeRead(
        full_name=intake.full_name,
        headline=intake.headline,
        location=intake.location,
        email=intake.email,
        phone=intake.phone,
        summary=intake.summary,
        skills=list(intake.skills),
        languages=list(intake.languages),
        experiences=[
            IntakeExperienceRead(
                role=entry.role,
                company=entry.company,
                employment_type=entry.employment_type,
                location=entry.location,
                started_on=entry.started_on,
                ended_on=entry.ended_on,
                is_current=entry.is_current,
                period_text=entry.period_text,
                summary=entry.summary,
                responsibilities=list(entry.responsibilities),
                technologies=list(entry.technologies),
                is_complete=entry.is_complete,
            )
            for entry in intake.experiences
        ],
        education=[
            IntakeEducationRead(
                institution=entry.institution, degree=entry.degree, period_text=entry.period_text
            )
            for entry in intake.education
        ],
        projects=[
            IntakeProjectRead(
                name=entry.name,
                description=entry.description,
                technologies=list(entry.technologies),
            )
            for entry in intake.projects
        ],
        certifications=list(intake.certifications),
        warnings=list(intake.warnings),
        resume_text=source.text,
        resume_filename=source.filename,
    )


async def read_upload(
    session: AsyncSession, user: User, *, filename: str, content: bytes
) -> ResumeIntakeRead:
    """Store the uploaded file and read a proposal out of it.

    The file is stored through the same path the profile page uses, so the size
    and type limits, the per-user filename and the audit entry are the existing
    ones rather than a second implementation. Extraction then runs against
    *this* upload's bytes even when the profile already holds resume text: the
    user is asking what this file says, and the stored text is only replaced if
    they confirm it.
    """
    suffix = Path(filename or "").suffix.lower()
    profile = await user_service.save_resume_file(
        session, user, filename=filename, content=content
    )
    text = await asyncio.to_thread(user_service.extract_resume_text, content, suffix)
    if not text:
        return ResumeIntakeRead(
            warnings=[
                "Não conseguimos ler o texto deste arquivo. Se ele for um PDF escaneado, "
                "cole o texto do currículo no seu perfil."
            ],
            resume_filename=profile.resume_filename,
        )

    intake = resume_intake.extract(text)
    logger.info(
        "Resume read for confirmation.",
        extra={
            "action": "profile.intake.read",
            "status": "ok",
            "user_id": user.id,
            "source": "upload",
            "positions": len(intake.experiences),
            "warnings": len(intake.warnings),
        },
    )
    return _to_read(intake, _Source(text=text, filename=profile.resume_filename))


async def read_stored(session: AsyncSession, user: User) -> ResumeIntakeRead:
    """Read a proposal out of the resume text already on the profile.

    The wizard's second entry point: a user who pasted their resume, or uploaded
    one before this existed, should not have to find the PDF again.
    """
    profile = await user_service.get_or_create_profile(session, user)
    text = (profile.resume_text or "").strip()
    if not text:
        raise ValidationError(
            "There is no resume to read yet. Upload a PDF or paste your resume text first."
        )

    intake = resume_intake.extract(text)
    logger.info(
        "Resume read for confirmation.",
        extra={
            "action": "profile.intake.read",
            "status": "ok",
            "user_id": user.id,
            "source": "stored",
            "positions": len(intake.experiences),
            "warnings": len(intake.warnings),
        },
    )
    return _to_read(intake, _Source(text=text, filename=profile.resume_filename))


async def apply(session: AsyncSession, user: User, payload: IntakeApply) -> IntakeApplied:
    """Write the confirmed proposal. Nothing the user left out is touched.

    Positions are appended, not merged: there is no identity to merge on, and
    silently updating a position the user thought they were adding is a worse
    failure than a duplicate they can delete. `replace_experiences` is the
    explicit way to start over, and it removes only this account's rows.
    """
    fields = payload.model_dump(
        exclude_unset=True,
        exclude={"experiences", "replace_experiences", "full_name"},
    )
    if fields:
        await user_service.update_profile(session, user, ProfileUpdate(**fields))

    # The display name lives on the account, not the profile, and is only filled
    # in when it is still blank: an existing name is something the user chose.
    if payload.full_name and not (user.full_name or "").strip():
        user.full_name = payload.full_name.strip()

    removed = 0
    if payload.replace_experiences:
        existing = await session.scalars(select(Experience.id).where(Experience.user_id == user.id))
        ids = list(existing)
        if ids:
            await session.execute(delete(Experience).where(Experience.id.in_(ids)))
            removed = len(ids)

    created = 0
    for entry in payload.experiences:
        await resume_service.create_experience(session, user, entry)
        created += 1

    await session.flush()
    profile = await session.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:  # pragma: no cover - update_profile creates it
        profile = await user_service.get_or_create_profile(session, user)

    logger.info(
        "Resume intake confirmed.",
        extra={
            "action": "profile.intake.apply",
            "status": "ok",
            "user_id": user.id,
            # Not `created`/`removed`: `created` is a reserved LogRecord
            # attribute and `makeRecord` raises on it (guard G7).
            "positions_created": created,
            "positions_removed": removed,
            "fields": sorted(fields),
        },
    )
    return IntakeApplied(
        profile=ProfileRead.model_validate(profile),
        experiences_created=created,
        experiences_removed=removed,
    )
