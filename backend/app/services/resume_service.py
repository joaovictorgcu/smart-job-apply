"""Each application's own resume: derive it, read it, edit it.

The master resume lives on the profile. This service is the only place that
turns it into the version one application presents, and it holds three rules
the feature stands on:

* **The master is a base, not a live dependency.** A version is derived once,
  with the master snapshotted into `base_document`. Editing the profile
  afterwards changes what the *next* application derives and nothing else.
* **Versions never share state.** Every application has its own row, so
  editing one cannot reach another. That is a property of the schema here, not
  a discipline the code has to keep remembering.
* **A version re-emphasizes; it never rewrites history.** An edit that changes
  a company, a role or a period — or introduces an experience the master never
  had — is refused, and the invention guard runs over every saved edit.

Nothing here commits: the request session commits once, at the end.
"""

from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.client import flag_unsupported_skills
from app.ai.scoring import profile_fingerprint, profile_source_text
from app.api.errors import NotFoundError, PreconditionFailedError, ValidationError
from app.domain.resume import (
    ResumeDocument,
    dump_document,
    identity_conflicts,
    parse_document,
    render_markdown,
    render_plain_text,
    tailor_for_posting,
)
from app.models import (
    Application,
    ApplicationEventType,
    Job,
    TailoredResume,
    User,
)
from app.observability import get_logger, record_event
from app.schemas.tailoring import ApplicationResumeRead
from app.services import user_service

logger = get_logger(__name__)

SOURCE_RULES = "rules"
SOURCE_USER = "user"


async def _get_application(session: AsyncSession, user: User, application_id: int) -> Application:
    """One application with its job, scoped to its owner.

    Scoped in the query rather than checked afterwards: this is how the resume
    endpoints resolve ownership, and one forgotten filter would hand another
    account's resume out.
    """
    result = await session.execute(
        select(Application)
        .options(selectinload(Application.job))
        .where(Application.id == application_id, Application.user_id == user.id)
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise NotFoundError("Application not found.")
    return application


async def _get_row(session: AsyncSession, user: User, job_id: int) -> TailoredResume | None:
    result = await session.execute(
        select(TailoredResume).where(
            TailoredResume.user_id == user.id, TailoredResume.job_id == job_id
        )
    )
    return result.scalar_one_or_none()


async def get_version(
    session: AsyncSession, user: User, application_id: int
) -> tuple[Application, TailoredResume] | None:
    """This application's resume version, or None when it has none yet.

    "None yet" is a normal state with two causes the UI words differently: a
    brand-new application whose master resume is empty, and an application
    prepared before this feature existed. Both are offered the same way out —
    derive one from the master as it stands now.
    """
    application = await _get_application(session, user, application_id)
    row = await _get_row(session, user, application.job_id)
    if row is None or not row.document:
        return None
    return application, row


def _posting_terms(job: Job | None) -> list[str]:
    """Extra posting text worth matching against, beyond title and description.

    The scoring pass already extracted what the posting demands; reusing it
    means a requirement stated once in a bullet list still counts, and it costs
    nothing.
    """
    if job is None:
        return []
    return [*(job.missing_requirements or []), *(job.score_reasons or [])]


async def _derive(
    session: AsyncSession,
    user: User,
    application: Application,
    *,
    row: TailoredResume | None,
) -> TailoredResume:
    """Derive (or re-derive) the version for one application from the master."""
    profile = await user_service.get_or_create_profile(session, user)
    master = user_service.master_document(profile)
    if master.is_empty:
        raise PreconditionFailedError(
            "Your master resume has no experiences, skills or technologies yet. Fill it in "
            "under Perfil and this application can have its own version of it."
        )

    job = application.job
    version = tailor_for_posting(
        master,
        title=job.title if job else None,
        description=job.description if job else None,
        extra=_posting_terms(job),
    )

    if row is None:
        row = TailoredResume(user_id=user.id, job_id=application.job_id)
        session.add(row)

    row.document = dump_document(version.document)
    row.base_document = dump_document(master)
    row.focus = list(version.focus)
    row.document_changes = [change.model_dump(mode="json") for change in version.changes]
    row.document_source = SOURCE_RULES
    # No invention is possible here by construction — every emphasized term came
    # out of the master — but the guard is still run and still recorded, because
    # "we proved it" and "we assumed it" are different claims.
    context = await user_service.build_profile_context(session, user)
    row.invention_flags = flag_unsupported_skills(
        profile_source_text(context), render_plain_text(version.document)
    )
    row.source_fingerprint = profile_fingerprint(context)
    await session.flush()

    logger.info(
        "Application resume derived from the master.",
        extra={
            "action": "resume.derive",
            "status": "ok",
            "user_id": user.id,
            "job_id": application.job_id,
            "application_id": application.id,
            "focus": len(row.focus),
            "changes": len(row.document_changes),
        },
    )
    return row


async def derive_version(
    session: AsyncSession, user: User, application_id: int
) -> tuple[Application, TailoredResume]:
    """Build this application's version from the master resume as it stands now.

    Also the way back: re-deriving discards the edits made to this version and
    starts again from the master, which is the "voltar ao currículo principal"
    the UI offers. It touches no other application.
    """
    application = await _get_application(session, user, application_id)
    row = await _get_row(session, user, application.job_id)
    return application, await _derive(session, user, application, row=row)


async def ensure_version(
    session: AsyncSession, user: User, application: Application
) -> TailoredResume | None:
    """Give a freshly created application its own version, if one is possible.

    Called from the two paths that create applications — the API and the
    automation engine — so "every application has its own resume" holds without
    the user asking for it.

    Returns None instead of raising when there is nothing to derive from: an
    empty master resume is a normal state for a new account, and refusing to
    create the application over it would be absurd. A stored resume that no
    longer validates is treated the same way and logged, for the same reason —
    the application still needs to exist so the user can fix the profile.
    """
    existing = await _get_row(session, user, application.job_id)
    if existing is not None and existing.document:
        return existing
    try:
        return await _derive(session, user, application, row=existing)
    except PreconditionFailedError:
        return None
    except PydanticValidationError as exc:
        logger.warning(
            "The stored master resume did not validate; the application was created "
            "without its own version.",
            extra={
                "action": "resume.derive",
                "status": "skipped",
                "user_id": user.id,
                "application_id": application.id,
                "errors": exc.error_count(),
            },
        )
        return None


async def update_version(
    session: AsyncSession, user: User, application_id: int, document: ResumeDocument
) -> tuple[Application, TailoredResume]:
    """Save the user's edits to one application's version.

    Refuses an edit that changes an experience's identity or introduces one the
    master never had: this version exists to present the same history
    differently, and a resume that quietly disagrees with the master about where
    someone worked is the failure mode the whole feature is built to avoid.

    Re-runs the invention guard over the saved text, because the user can
    introduce a claim the derivation never would.
    """
    application = await _get_application(session, user, application_id)
    row = await _get_row(session, user, application.job_id)
    if row is None or not row.document:
        raise NotFoundError(
            "This application has no resume version yet. Generate one from your master resume "
            "first."
        )

    base = parse_document(row.base_document)
    conflicts = identity_conflicts(base, document)
    if conflicts:
        raise ValidationError(
            "A version of your resume can re-emphasize an experience, not rewrite it. "
            "These entries do not match your master resume (company, role or period "
            f"changed, or the experience is not in it): {', '.join(conflicts)}. Edit your "
            "master resume under Perfil if the facts themselves changed."
        )

    row.document = dump_document(document)
    row.document_source = SOURCE_USER
    row.invention_flags = flag_unsupported_skills(
        profile_source_text(await user_service.build_profile_context(session, user)),
        render_plain_text(document),
    )
    await session.flush()
    await record_event(
        session,
        application_id=application.id,
        event_type=ApplicationEventType.RESUME_TAILORED,
        message="The user edited the resume this application presents.",
        payload={"invention_flags": len(row.invention_flags)},
        job_id=application.job_id,
        user_id=user.id,
    )

    logger.info(
        "Application resume edited.",
        extra={
            "action": "resume.edit",
            "status": "ok",
            "user_id": user.id,
            "application_id": application.id,
            "invention_flags": len(row.invention_flags),
        },
    )
    return application, row


async def current_fingerprint(session: AsyncSession, user: User) -> str:
    """Fingerprint of the master resume as it stands now, for staleness."""
    return profile_fingerprint(await user_service.build_profile_context(session, user))


def to_read(
    application: Application, row: TailoredResume, *, current: str | None
) -> ApplicationResumeRead:
    """Build the response, including the diff base and the staleness verdict."""
    document = parse_document(row.document)
    job = application.job
    return ApplicationResumeRead(
        application_id=application.id,
        job_id=row.job_id,
        job_title=job.title if job else None,
        job_company=job.company if job else None,
        document=document,
        base_document=parse_document(row.base_document),
        focus=list(row.focus or []),
        changes=list(row.document_changes or []),
        invention_flags=list(row.invention_flags or []),
        source=row.document_source or SOURCE_RULES,
        is_stale=bool(row.source_fingerprint and current and row.source_fingerprint != current),
        markdown=render_markdown(document),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
