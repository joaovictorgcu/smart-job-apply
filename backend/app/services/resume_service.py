"""The master resume, and the copy each application carries.

Layering: `app.domain.resume` decides *what* the adapted document is (pure, no
database), this module decides *when* one is written and to which row. That split
is what lets the isolation rules be tested against plain data and enforced in
exactly one place here.

Three rules govern every write below, and they are the feature:

1. A new application derives from the master resume **as it stands now**.
2. Writing the master never touches an existing application's copy — the copy
   holds its own strings, so there is no path from one to the other.
3. Writing one application's copy never touches the master or a sibling — every
   query in this module is keyed on a single `application_id`.

Nothing here commits: the request session commits once, at the end.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import NotFoundError, PreconditionFailedError, ValidationError
from app.config import get_settings
from app.database.base import utcnow
from app.domain import resume as domain
from app.domain import resume_diff, resume_render
from app.models import (
    Application,
    ApplicationEventType,
    ApplicationResume,
    Experience,
    Job,
    User,
)
from app.observability import get_logger, record_event
from app.schemas.resume import (
    AdaptedExperience,
    AdaptedProject,
    ApplicationResumeRead,
    ApplicationResumeUpdate,
    ExperienceCreate,
    ExperienceMoveRead,
    ExperienceRead,
    ExperienceUpdate,
    FitFactor,
    MasterResumeRead,
    ResumeChange,
    ResumeComparisonRead,
    ResumeVersionSummary,
)
from app.services import preference_service, resume_pdf, user_service

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# The master resume
# --------------------------------------------------------------------------- #


async def list_experiences(session: AsyncSession, user: User) -> list[Experience]:
    """This user's positions, in the order the master resume shows them.

    `position` first, then most recent, then id — so a user who has never
    reordered anything still gets reverse-chronological, and two positions added
    in the same request never swap places between requests.
    """
    result = await session.execute(
        select(Experience)
        .where(Experience.user_id == user.id)
        .order_by(
            Experience.position,
            Experience.is_current.desc(),
            Experience.ended_on.desc().nullslast(),
            Experience.started_on.desc().nullslast(),
            Experience.id,
        )
    )
    return list(result.scalars().all())


def _to_domain_experience(row: Experience) -> domain.ExperienceInput:
    return domain.ExperienceInput(
        experience_id=row.id,
        company=row.company,
        role=row.role,
        location=row.location,
        employment_type=row.employment_type,
        started_on=row.started_on,
        ended_on=row.ended_on,
        is_current=bool(row.is_current),
        summary=row.summary or "",
        responsibilities=tuple(row.responsibilities or []),
        technologies=tuple(row.technologies or []),
        results=tuple(row.results or []),
        projects=tuple(
            domain.ProjectEntry(
                name=str(project.get("name") or ""),
                description=str(project.get("description") or ""),
                technologies=tuple(str(term) for term in (project.get("technologies") or [])),
            )
            for project in (row.projects or [])
        ),
        position=row.position,
    )


async def build_master(session: AsyncSession, user: User) -> domain.MasterResume:
    """Snapshot the master resume for the derivation — profile text plus positions."""
    profile = await user_service.get_or_create_profile(session, user)
    experiences = await list_experiences(session, user)
    return domain.MasterResume(
        full_name=user.full_name,
        headline=profile.headline,
        location=profile.location,
        summary=profile.summary,
        years_of_experience=profile.years_of_experience,
        skills=tuple(profile.skills or []),
        resume_text=profile.resume_text or "",
        experiences=tuple(_to_domain_experience(row) for row in experiences),
    )


async def read_master(session: AsyncSession, user: User) -> MasterResumeRead:
    """The master resume as one document, with the fingerprint snapshots compare to."""
    profile = await user_service.get_or_create_profile(session, user)
    experiences = await list_experiences(session, user)
    master = await build_master(session, user)
    return MasterResumeRead(
        headline=profile.headline,
        location=profile.location,
        summary=profile.summary,
        years_of_experience=profile.years_of_experience,
        skills=list(profile.skills or []),
        resume_text=profile.resume_text,
        resume_filename=profile.resume_filename,
        experiences=[ExperienceRead.model_validate(row) for row in experiences],
        fingerprint=domain.fingerprint(master),
        updated_at=profile.updated_at,
    )


async def _next_position(session: AsyncSession, user: User) -> int:
    highest = await session.scalar(
        select(func.max(Experience.position)).where(Experience.user_id == user.id)
    )
    return int(highest) + 1 if highest is not None else 0


def _project_dicts(projects: Any) -> list[dict[str, Any]]:
    return [project.model_dump(mode="json") for project in (projects or [])]


async def create_experience(
    session: AsyncSession, user: User, payload: ExperienceCreate
) -> Experience:
    """Append one position to the master resume.

    Existing application snapshots are deliberately untouched: they are what
    those applications already present, and rewriting them because the user
    remembered an old job would change a document a human may have approved.
    They read as stale, and the user re-adapts the ones they care about.
    """
    row = Experience(
        user_id=user.id,
        company=payload.company.strip(),
        role=payload.role.strip(),
        employment_type=payload.employment_type,
        location=payload.location,
        started_on=payload.started_on,
        ended_on=payload.ended_on,
        is_current=payload.is_current,
        summary=payload.summary,
        responsibilities=[line for line in payload.responsibilities if line.strip()],
        technologies=[term for term in payload.technologies if term.strip()],
        results=[line for line in payload.results if line.strip()],
        projects=_project_dicts(payload.projects),
        position=(
            payload.position
            if payload.position is not None
            else await _next_position(session, user)
        ),
    )
    session.add(row)
    await session.flush()
    logger.info(
        "Experience added.",
        extra={
            "action": "resume.experience.create",
            "status": "ok",
            "user_id": user.id,
            "experience_id": row.id,
        },
    )
    return row


async def get_experience(session: AsyncSession, user: User, experience_id: int) -> Experience:
    result = await session.execute(
        select(Experience).where(Experience.id == experience_id, Experience.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("Experience not found.")
    return row


async def update_experience(
    session: AsyncSession, user: User, experience_id: int, payload: ExperienceUpdate
) -> Experience:
    """Edit one position on the master resume. Only the fields sent are touched."""
    row = await get_experience(session, user, experience_id)
    changes = payload.model_dump(exclude_unset=True)

    if "projects" in changes and payload.projects is not None:
        changes["projects"] = _project_dicts(payload.projects)
    for listed in ("responsibilities", "results"):
        if changes.get(listed) is not None:
            changes[listed] = [line for line in changes[listed] if str(line).strip()]
    if changes.get("technologies") is not None:
        changes["technologies"] = [term for term in changes["technologies"] if str(term).strip()]

    for field, value in changes.items():
        setattr(row, field, value)

    # Re-check the invariants on the *merged* row: a partial update can break a
    # period that was valid before it, exactly as `update_settings` re-checks its
    # ranges rather than only the incoming ones.
    if row.started_on and row.ended_on and row.ended_on < row.started_on:
        raise ValidationError("ended_on cannot be earlier than started_on.")
    if row.is_current and row.ended_on is not None:
        raise ValidationError("A current position cannot have an end date.")

    await session.flush()
    logger.info(
        "Experience updated.",
        extra={
            "action": "resume.experience.update",
            "status": "ok",
            "user_id": user.id,
            "experience_id": row.id,
            "fields": sorted(changes),
        },
    )
    return row


async def delete_experience(session: AsyncSession, user: User, experience_id: int) -> None:
    """Remove a position from the master resume, and only from the master.

    Snapshots that quoted it keep quoting it. Deleting a job from the master is
    not a claim that no application ever mentioned it, and rewriting history in
    already-reviewed documents would be worse than leaving them stale.
    """
    row = await get_experience(session, user, experience_id)
    await session.delete(row)
    await session.flush()


# --------------------------------------------------------------------------- #
# One application's copy
# --------------------------------------------------------------------------- #


def _application_query() -> Select[tuple[Application]]:
    return select(Application).options(selectinload(Application.job))


async def _load_application(
    session: AsyncSession, user_id: int, application_id: int
) -> Application | None:
    """Fetch an application scoped to its owner, with its job loaded.

    Scoped in the query rather than filtered afterwards: this is the only way an
    application is resolved in this module, and one forgotten `user_id` would
    hand another account's resume out.
    """
    result = await session.execute(
        _application_query().where(Application.id == application_id, Application.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_application_resume(
    session: AsyncSession, user: User, application_id: int
) -> ApplicationResume | None:
    """The stored copy for one application, or None. Scoped to the owner."""
    result = await session.execute(
        select(ApplicationResume).where(
            ApplicationResume.application_id == application_id,
            ApplicationResume.user_id == user.id,
        )
    )
    return result.scalar_one_or_none()


def _write_snapshot(
    row: ApplicationResume, adapted: domain.AdaptedResume, *, model: str | None = None
) -> None:
    """Copy a derivation onto a row. Every string ends up owned by this row."""
    row.headline = adapted.headline
    row.summary = adapted.summary
    row.skills = list(adapted.skills)
    row.highlighted_skills = list(adapted.highlighted_skills)
    row.emphasized_technologies = list(adapted.emphasized_technologies)
    row.experiences = [experience.as_dict() for experience in adapted.experiences]
    row.projects = [dict(project) for project in adapted.projects]
    row.changes = [change.as_dict() for change in adapted.changes]
    row.fit_score = adapted.fit_score
    row.fit_factors = [factor.as_dict() for factor in adapted.fit_factors]
    row.uncovered_requirements = list(adapted.uncovered_requirements)
    row.source_fingerprint = adapted.fingerprint
    row.model = model
    row.was_edited = False
    row.adapted_at = utcnow()


def _target(job: Job | None, priority: Sequence[str] = ()) -> domain.JobTarget:
    if job is None:
        return domain.JobTarget(priority_terms=tuple(priority))
    return domain.JobTarget(
        title=job.title or "",
        company=job.company or "",
        description=job.description or "",
        location=job.location,
        priority_terms=tuple(priority),
    )


async def _derive(
    session: AsyncSession, user: User, application: Application
) -> ApplicationResume | None:
    """Derive and persist this application's copy. None when there is nothing to adapt."""
    master = await build_master(session, user)
    if master.is_empty():
        return None

    # The candidate's stated priorities only reorder what this posting already
    # asks about, so a derivation stays a derivation of *this* vacancy.
    rules = await preference_service.rules_for(session, user.id)
    adapted = domain.adapt(master, _target(application.job, rules.priority_technologies))
    row = await get_application_resume(session, user, application.id)
    if row is None:
        row = ApplicationResume(
            user_id=user.id,
            application_id=application.id,
            job_id=application.job_id,
            version=1,
        )
        session.add(row)
    else:
        # A fresh derivation is a new version of *this* application's document.
        # Nothing else in the table moves; siblings are separate rows and the
        # master is a separate table.
        row.version = int(row.version or 1) + 1
        row.job_id = application.job_id

    _write_snapshot(row, adapted)
    await session.flush()
    return row


async def adapt_application_resume(
    session: AsyncSession, user: User, application_id: int
) -> ApplicationResume:
    """Adapt (or adapt again) the resume this application presents.

    Raises `PreconditionFailedError` when the master resume is empty — there is
    nothing to reorganise, and an empty document would be a worse answer than
    telling the user to fill in their experience first.
    """
    application = await _load_application(session, user.id, application_id)
    if application is None:
        raise NotFoundError("Application not found.")

    row = await _derive(session, user, application)
    if row is None:
        raise PreconditionFailedError(
            "Add your experience (or your resume text) in Profile before adapting — "
            "there is nothing to reorganise yet."
        )

    await record_event(
        session,
        application_id=application.id,
        event_type=ApplicationEventType.RESUME_ADAPTED,
        message="The resume for this application was derived from the master resume.",
        payload={
            "version": row.version,
            "fit_score": row.fit_score,
            "experiences": len(row.experiences or []),
            "emphasized": list(row.emphasized_technologies or []),
        },
        job_id=application.job_id,
        user_id=user.id,
    )
    logger.info(
        "Application resume adapted.",
        extra={
            "action": "resume.adapt",
            "status": "ok",
            "user_id": user.id,
            "application_id": application.id,
            "job_id": application.job_id,
            "version": row.version,
            "fit_score": row.fit_score,
        },
    )
    return row


async def ensure_application_resume(
    session: AsyncSession, user_id: int, application_id: int
) -> ApplicationResume | None:
    """Give a brand-new application its copy, derived from the master as it stands.

    Idempotent and quiet, because it runs on the creation path — from the API and
    from the automation engine's prepare run alike. An account with no experience
    yet, or an application whose job vanished, must not fail the thing it is a
    side effect of, so this returns None instead of raising.
    """
    existing = await session.execute(
        select(ApplicationResume).where(
            ApplicationResume.application_id == application_id,
            ApplicationResume.user_id == user_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row

    application = await _load_application(session, user_id, application_id)
    if application is None:
        return None
    user = await session.get(User, user_id)
    if user is None:
        return None

    row = await _derive(session, user, application)
    if row is None:
        return None

    await record_event(
        session,
        application_id=application.id,
        event_type=ApplicationEventType.RESUME_ADAPTED,
        message="A resume was derived for this application from the master resume.",
        payload={"version": row.version, "fit_score": row.fit_score, "automatic": True},
        job_id=application.job_id,
        user_id=user_id,
    )
    return row


async def update_application_resume(
    session: AsyncSession, user: User, application_id: int, payload: ApplicationResumeUpdate
) -> ApplicationResume:
    """Save the reviewer's edits to one application's copy — and nothing else.

    The write is keyed on a single `application_id`, so there is no query here
    that could reach the master resume or another application. `experiences` is
    positional and must match the stored length: an editor built against an
    older derivation would otherwise silently move one job's bullets onto
    another, which is the worst possible way for this to fail.
    """
    row = await get_application_resume(session, user, application_id)
    if row is None:
        raise NotFoundError("This application has no resume yet. Adapt one first.")

    changes = payload.model_dump(exclude_unset=True)
    if "headline" in changes:
        row.headline = payload.headline
    if "summary" in changes:
        row.summary = payload.summary
    if payload.skills is not None:
        row.skills = [skill for skill in payload.skills if skill.strip()]

    if payload.experiences is not None:
        stored = list(row.experiences or [])
        if len(payload.experiences) != len(stored):
            raise ValidationError(
                "This resume has "
                f"{len(stored)} experience(s), but {len(payload.experiences)} were sent. "
                "Reload the application and try again."
            )
        merged: list[dict[str, Any]] = []
        for entry, edit in zip(stored, payload.experiences, strict=True):
            # Identity and the derivation's own report survive the edit; only the
            # text the reviewer can see and change is replaced.
            merged.append(
                {
                    **entry,
                    "summary": edit.summary,
                    "responsibilities": [line for line in edit.responsibilities if line.strip()],
                    "technologies": [term for term in edit.technologies if term.strip()],
                    "results": [line for line in edit.results if line.strip()],
                }
            )
        row.experiences = merged

    row.was_edited = True
    await session.flush()
    logger.info(
        "Application resume edited.",
        extra={
            "action": "resume.edit",
            "status": "ok",
            "user_id": user.id,
            "application_id": application_id,
            "fields": sorted(changes),
        },
    )
    return row


async def list_versions(session: AsyncSession, user: User) -> list[ResumeVersionSummary]:
    """Every version this user has, newest first — the "other versions" list.

    One query with the application and job joined in: the point of the list is to
    show that the versions are per-vacancy and independent, and N+1 lookups to
    render four rows would be a poor way to prove it.
    """
    master = await build_master(session, user)
    current = domain.fingerprint(master)

    result = await session.execute(
        select(ApplicationResume, Application, Job)
        .join(Application, Application.id == ApplicationResume.application_id)
        .join(Job, Job.id == ApplicationResume.job_id)
        .where(ApplicationResume.user_id == user.id)
        .order_by(ApplicationResume.updated_at.desc(), ApplicationResume.id.desc())
    )
    return [
        ResumeVersionSummary(
            application_id=row.application_id,
            job_id=row.job_id,
            job_title=job.title,
            job_company=job.company,
            application_status=application.status,
            version=row.version,
            fit_score=row.fit_score,
            has_fit=bool(row.fit_factors),
            highlighted_count=len(row.emphasized_technologies or []),
            was_edited=row.was_edited,
            is_stale=_is_stale(row, current),
            updated_at=row.updated_at,
        )
        for row, application, job in result.all()
    ]


def _is_stale(row: ApplicationResume, current: str | None) -> bool:
    return bool(row.source_fingerprint and current and row.source_fingerprint != current)


def _iso_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        # A hand-edited database or a format from an older release; the document
        # is still readable without the period, so this must not be fatal.
        return None


def _read_project(raw: dict[str, Any]) -> AdaptedProject:
    return AdaptedProject(
        name=str(raw.get("name") or ""),
        description=str(raw.get("description") or ""),
        technologies=[str(term) for term in (raw.get("technologies") or [])],
        company=str(raw.get("company") or ""),
        role=str(raw.get("role") or ""),
        matched_terms=[str(term) for term in (raw.get("matched_terms") or [])],
    )


def _read_experience(raw: dict[str, Any]) -> AdaptedExperience:
    return AdaptedExperience(
        experience_id=raw.get("experience_id"),
        company=str(raw.get("company") or ""),
        role=str(raw.get("role") or ""),
        location=raw.get("location"),
        employment_type=raw.get("employment_type"),
        started_on=_iso_date(raw.get("started_on")),
        ended_on=_iso_date(raw.get("ended_on")),
        is_current=bool(raw.get("is_current")),
        summary=str(raw.get("summary") or ""),
        responsibilities=[str(line) for line in (raw.get("responsibilities") or [])],
        technologies=[str(term) for term in (raw.get("technologies") or [])],
        results=[str(line) for line in (raw.get("results") or [])],
        projects=[_read_project(project) for project in (raw.get("projects") or [])],
        relevance=int(raw.get("relevance") or 0),
        matched_terms=[str(term) for term in (raw.get("matched_terms") or [])],
        promoted=int(raw.get("promoted") or 0),
    )


def _snapshot_of(row: ApplicationResume) -> resume_diff.Snapshot:
    """The stored copy as plain data, exactly as saved.

    Feeds both the comparison and the rendered document, so the PDF an employer
    receives and the diff the user approved are built from one object.
    """
    return resume_diff.Snapshot(
        summary=row.summary or "",
        skills=tuple(row.skills or []),
        emphasized_technologies=tuple(row.emphasized_technologies or []),
        experiences=tuple(
            resume_diff.SnapshotExperience(
                experience_id=entry.get("experience_id"),
                company=str(entry.get("company") or ""),
                role=str(entry.get("role") or ""),
                summary=str(entry.get("summary") or ""),
                responsibilities=tuple(
                    str(line) for line in (entry.get("responsibilities") or [])
                ),
                technologies=tuple(str(term) for term in (entry.get("technologies") or [])),
                results=tuple(str(line) for line in (entry.get("results") or [])),
                matched_terms=tuple(str(term) for term in (entry.get("matched_terms") or [])),
                promoted=int(entry.get("promoted") or 0),
                period=resume_render.period_text(
                    _iso_date(entry.get("started_on")),
                    _iso_date(entry.get("ended_on")),
                    bool(entry.get("is_current")),
                ),
                location=entry.get("location"),
            )
            for entry in (row.experiences or [])
        ),
    )


async def render_application_pdf(
    session: AsyncSession, user_id: int, application_id: int
) -> Path | None:
    """Write this application's adapted resume as the PDF the form attaches.

    Returns the path, or `None` when there is nothing honest to draw — no
    snapshot yet, or one the renderer refused. The caller falls back to the
    profile's uploaded PDF, which is what happened before this existed: a
    submission must never be blocked by a layout engine.

    Rewritten on every call rather than cached behind a timestamp. It is a page
    of text, it costs milliseconds, and a stale file attached to a real
    application is a far worse failure than the work of redrawing one.
    """
    result = await session.execute(
        select(ApplicationResume).where(
            ApplicationResume.application_id == application_id,
            ApplicationResume.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    user = await session.get(User, user_id)
    profile = await user_service.get_or_create_profile(session, user) if user else None
    contact = [
        value
        for value in (profile.location if profile else None, profile.phone if profile else None)
        if value
    ]

    blocks = resume_render.render_blocks(
        _snapshot_of(row),
        full_name=user.full_name if user else None,
        headline=row.headline,
        contact=contact,
    )
    try:
        content = resume_pdf.to_pdf(blocks)
    except resume_pdf.ResumeRenderError:
        # Already logged by the renderer. The caller attaches the uploaded PDF.
        return None

    target = get_settings().resumes_dir / application_pdf_name(user_id, application_id)
    await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(target.write_bytes, content)
    logger.info(
        "Adapted resume rendered.",
        extra={
            "action": "resume.pdf",
            "status": "ok",
            "user_id": user_id,
            "application_id": application_id,
            "bytes": len(content),
        },
    )
    return target


async def read_application_pdf(
    session: AsyncSession, user: User, application_id: int
) -> bytes:
    """The adapted resume's PDF bytes, for a download.

    Drawn on demand rather than served off disk: the stored copy is the source
    of truth, and a file written before the user's last edit would hand them a
    document that is not the one on their screen.
    """
    path = await render_application_pdf(session, user.id, application_id)
    if path is None:
        raise PreconditionFailedError(
            "This application has no adapted resume to download yet. Adapt one first."
        )
    return await asyncio.to_thread(path.read_bytes)


def application_pdf_name(user_id: int, application_id: int) -> str:
    """The per-application file name. Scoped by user so no two accounts collide."""
    return f"user_{user_id}_application_{application_id}.pdf"


def build_comparison(
    row: ApplicationResume, master: domain.MasterResume, *, is_stale: bool
) -> ResumeComparisonRead:
    """Diff this copy against the master it came from, and count the edits.

    Skipped when the copy is stale: the master has moved since, so the diff
    would attribute the user's own profile edits to the adaptation.
    """
    result = resume_diff.compare(
        master_experience_ids=[entry.experience_id for entry in master.experiences],
        master_skills=list(master.skills),
        master_text=master.searchable(),
        snapshot=_snapshot_of(row),
        is_comparable=not is_stale,
    )
    return ResumeComparisonRead(
        moves=[
            ExperienceMoveRead(
                experience_id=move.experience_id,
                company=move.company,
                role=move.role,
                from_position=move.from_position,
                to_position=move.to_position,
                promoted_bullets=move.promoted_bullets,
                matched_terms=list(move.matched_terms),
            )
            for move in result.moves
        ],
        highlighted_technologies=list(result.highlighted_technologies),
        promoted_bullets=result.promoted_bullets,
        invented=list(result.invented),
        experiences_reordered=result.experiences_reordered,
        sections_adjusted=result.sections_adjusted,
        changes_total=result.changes_total,
        is_clean=result.is_clean,
        is_comparable=result.is_comparable,
    )


def to_read(
    row: ApplicationResume,
    *,
    job: Job | None,
    current_fingerprint: str | None,
    comparison: ResumeComparisonRead | None = None,
) -> ApplicationResumeRead:
    """Build the response, computing staleness against the master resume now."""
    return ApplicationResumeRead(
        application_id=row.application_id,
        job_id=row.job_id,
        job_title=job.title if job else None,
        job_company=job.company if job else None,
        version=row.version,
        headline=row.headline,
        summary=row.summary,
        skills=list(row.skills or []),
        highlighted_skills=list(row.highlighted_skills or []),
        emphasized_technologies=list(row.emphasized_technologies or []),
        experiences=[_read_experience(entry) for entry in (row.experiences or [])],
        projects=[_read_project(project) for project in (row.projects or [])],
        changes=[
            ResumeChange(
                kind=str(change.get("kind") or ""),
                target=str(change.get("target") or ""),
                terms=[str(term) for term in (change.get("terms") or [])],
                matched=int(change.get("matched") or 0),
                total=int(change.get("total") or 0),
            )
            for change in (row.changes or [])
        ],
        fit_score=row.fit_score,
        fit_factors=[
            FitFactor(
                factor=str(factor.get("factor") or ""),
                score=int(factor.get("score") or 0),
                weight_pct=int(factor.get("weight_pct") or 0),
                matched=int(factor.get("matched") or 0),
                total=int(factor.get("total") or 0),
                terms=[str(term) for term in (factor.get("terms") or [])],
            )
            for factor in (row.fit_factors or [])
        ],
        uncovered_requirements=list(row.uncovered_requirements or []),
        comparison=comparison,
        model=row.model,
        was_edited=row.was_edited,
        is_stale=_is_stale(row, current_fingerprint),
        adapted_at=row.adapted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def read_for_application(
    session: AsyncSession, user: User, application_id: int
) -> ApplicationResumeRead:
    """The stored copy for one application, or 404."""
    row = await get_application_resume(session, user, application_id)
    if row is None:
        raise NotFoundError("This application has no adapted resume yet.")
    application = await _load_application(session, user.id, application_id)
    master = await build_master(session, user)
    current = domain.fingerprint(master)
    stale = _is_stale(row, current)
    return to_read(
        row,
        job=application.job if application else None,
        current_fingerprint=current,
        comparison=build_comparison(row, master, is_stale=stale),
    )
