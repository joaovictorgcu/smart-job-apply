"""Per-application resumes: derive one, guard it, store it, edit it.

The shape of this layer follows one decision. `app.domain.resume` computes the
whole of an application's resume deterministically and offline — which
experiences lead, which of their bullets, which skills come first, which
technologies matched, and the Markdown that renders all of it. That is the
default and the thing the screen depends on. A model rewriting the prose is a
second step the user asks for explicitly. So:

* every derivation produces `sections` and `focus`, with or without an API key,
  which is what makes the feature demonstrable and its behaviour testable;
* the invention guard runs over whatever ends up in `content`, from either path,
  because "the generator promised not to invent" is not evidence.

Isolation is the other half. A derivation freezes `base_snapshot` — the master
resume exactly as it stood — so editing the profile later changes the master and
every *future* derivation, and cannot reach back into an application that
already has its own version. `source_fingerprint` reports that divergence as
`is_stale` rather than silently rewriting anything.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import flag_unsupported_skills
from app.ai.scoring import profile_fingerprint, profile_source_text
from app.api.errors import NotFoundError, PreconditionFailedError, UpstreamError
from app.automation.contracts import ProfileContext
from app.config import get_settings
from app.domain.resume import Derivation, MasterResume, derive
from app.models import Application, Job, TailoredResume, User
from app.observability import get_logger
from app.schemas.tailoring import (
    ApplicationResumeRead,
    CVChangeOut,
    ResumeFocusOut,
    ResumeSectionsOut,
    TailoredResumeRead,
)
from app.services import job_service, user_service

logger = get_logger(__name__)

# How `content` was produced. `deterministic` is the domain engine's markdown;
# `ai` means a model wrote the prose over the same computed structure.
#
# `deterministic` is the default, and that is a deliberate choice rather than a
# fallback. The screen shows the document *and* the derivation that produced it —
# which experiences lead, which bullets were kept, which skills were promoted —
# and those two have to agree, or the explanation is describing a document the
# user is not reading. The domain engine's markdown is that derivation rendered,
# so they agree by construction. A model rewriting the prose is a second,
# explicit step the user asks for, taken with the derivation still on screen as
# the record of what the version was built from.
Strategy = Literal["deterministic", "ai"]

STRATEGY_DETERMINISTIC: Strategy = "deterministic"
STRATEGY_AI: Strategy = "ai"


async def current_fingerprint(session: AsyncSession, user: User) -> str:
    """Fingerprint of the user's profile as it stands now (for staleness checks).

    The hashing itself lives in `app.ai.scoring` because the score history needs
    the same scheme: a resume draft and a score both go stale against the same
    profile edit, and two fingerprint schemes could not be compared.
    """
    return profile_fingerprint(await user_service.build_profile_context(session, user))


async def get_tailored_resume(
    session: AsyncSession, user: User, job_id: int
) -> TailoredResume | None:
    """The stored version for one job, or None. Scoped to the user for isolation."""
    result = await session.execute(
        select(TailoredResume).where(
            TailoredResume.user_id == user.id, TailoredResume.job_id == job_id
        )
    )
    return result.scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Deriving
# --------------------------------------------------------------------------- #


def _resolve_strategy(requested: Strategy) -> Strategy:
    """Refuse the AI wording loudly when there is no key, rather than substituting.

    Silently handing back the deterministic document would leave the user looking
    at a resume they did not ask for, wondering why "rewrite with AI" changed
    nothing.
    """
    if requested != STRATEGY_AI:
        return STRATEGY_DETERMINISTIC
    if not get_settings().ai_enabled:
        raise PreconditionFailedError(
            "AI features are not configured, so the wording cannot be rewritten. The "
            "version built from your own resume is still tailored to this posting."
        )
    return STRATEGY_AI


def _persist(
    session: AsyncSession,
    *,
    user: User,
    job: Job,
    row: TailoredResume | None,
    derivation: Derivation,
    profile: ProfileContext,
    content: str,
    strategy: Strategy,
    changes: list[dict[str, Any]],
    unsupported: list[str],
    stretch_flags: list[dict[str, Any]],
    summary: str | None,
    model: str | None,
) -> TailoredResume:
    """Write one application's version, replacing any previous one for that job."""
    if row is None:
        row = TailoredResume(user_id=user.id, job_id=job.id)
        session.add(row)

    row.content = content
    row.changes = changes
    row.unsupported_requirements = unsupported
    # Guards the text that actually ships, whichever path wrote it. The
    # deterministic path draws every word from the master, so a flag here is a
    # genuine signal — most often the posting's own spelling of a technology the
    # user records differently — rather than routine noise.
    row.invention_flags = flag_unsupported_skills(profile_source_text(profile), content)
    row.stretch_flags = stretch_flags
    row.summary = summary
    row.model = model
    row.source_fingerprint = profile_fingerprint(profile)
    row.was_edited = False
    row.sections = derivation.sections.as_dict()
    row.focus = derivation.focus.as_dict()
    # The isolation guarantee. Written on every derivation so the snapshot always
    # describes the master this exact version came from.
    row.base_snapshot = MasterResume.from_profile(profile).as_dict()
    row.strategy = strategy
    return row


async def derive_for_job(
    session: AsyncSession,
    user: User,
    job_id: int,
    *,
    strategy: Strategy = STRATEGY_DETERMINISTIC,
) -> TailoredResume:
    """Build (or rebuild) the resume for one job's application.

    The single writer. Both entry points — the job-scoped AI endpoint and the
    application-scoped one — come through here, so a row can never end up with
    prose from one design and structure from another.

    Raises `PreconditionFailedError` when there is nothing to tailor, and
    `UpstreamError` when the AI was asked for and returned nothing usable.
    """
    from app.ai import tailor_resume as ai_tailor_resume

    job = await job_service.get_job(session, user, job_id)
    if not job.description:
        raise PreconditionFailedError(
            "This job has no description yet. Run a search with analysis enabled first."
        )

    profile = await user_service.build_profile_context(session, user)
    master = MasterResume.from_profile(profile)
    if master.is_empty:
        raise PreconditionFailedError(
            "Add your resume in Profile before tailoring — there is nothing to adapt yet."
        )

    resolved = _resolve_strategy(strategy)
    if resolved == STRATEGY_AI and not (profile.resume_text or "").strip():
        # The AI path reads the free-text resume as its source of truth. A
        # structured-only profile has plenty to derive from but nothing for the
        # model to rewrite, so it is sent down the deterministic path rather
        # than handed an empty document to invent from.
        resolved = STRATEGY_DETERMINISTIC

    derivation = derive(master, job)
    settings_row = await user_service.get_or_create_settings(session, user)
    row = await get_tailored_resume(session, user, job_id)

    if resolved == STRATEGY_DETERMINISTIC:
        return _persist(
            session,
            user=user,
            job=job,
            row=row,
            derivation=derivation,
            profile=profile,
            content=derivation.content,
            strategy=STRATEGY_DETERMINISTIC,
            changes=list(derivation.changes),
            unsupported=list(derivation.unsupported_requirements),
            stretch_flags=[],
            summary=_deterministic_summary(derivation),
            model=None,
        )

    # The AI call happens before anything is written: a refusal must leave no row
    # behind, so that "generate again" starts from the same place it did before.
    result = await ai_tailor_resume(
        session, user=user, job=job, profile_ctx=profile, settings_row=settings_row
    )
    if result is None or not result.tailored_markdown.strip():
        raise UpstreamError(
            "The AI did not return a tailored resume. Try again, or use the version "
            "built from your own wording."
        )

    return _persist(
        session,
        user=user,
        job=job,
        row=row,
        derivation=derivation,
        profile=profile,
        content=result.tailored_markdown,
        strategy=STRATEGY_AI,
        # The model's own edit log, plus the structural moves the derivation
        # made underneath it — the reordering the UI shows came from the
        # derivation, so dropping it would leave the change list contradicting
        # the sections displayed next to it.
        changes=[change.model_dump(mode="json") for change in result.changes]
        + list(derivation.changes),
        # Union of both readings of "the posting wants this and the resume cannot
        # back it": the model's judgement, and the vocabulary check. Order is
        # the model's first, deduplicated case-insensitively.
        unsupported=_merge_unsupported(
            list(result.unsupported_requirements), derivation.unsupported_requirements
        ),
        stretch_flags=[flag.model_dump(mode="json") for flag in result.stretch_flags],
        summary=result.summary,
        model=settings_row.ai_model or get_settings().anthropic_model,
    )


def _deterministic_summary(derivation: Derivation) -> str:
    """One line on how this version was built, in the resume's own language."""
    focus = derivation.focus
    matched = ", ".join(focus.keywords[:6])
    if derivation.sections.language == "en":
        target = focus.title or "this posting"
        return (
            f"Reordered and re-emphasized your own resume for {target}"
            + (f", leading with {matched}." if matched else ".")
        )
    target = focus.title or "esta vaga"
    return (
        f"Seu próprio currículo reorganizado e reenfatizado para {target}"
        + (f", começando por {matched}." if matched else ".")
    )


def _merge_unsupported(primary: list[str], secondary: list[str]) -> list[str]:
    """Concatenate two gap lists, keeping the first spelling of each item."""
    merged: dict[str, str] = {}
    for item in (*primary, *secondary):
        text = item.strip()
        if text:
            merged.setdefault(text.casefold(), text)
    return list(merged.values())


async def create_tailored_resume(session: AsyncSession, user: User, job_id: int) -> TailoredResume:
    """Generate the AI-written version for one job — the original endpoint's path.

    Kept as its own function, and kept strict: this is what `POST
    /api/ai/tailor-cv/{job_id}` has always meant, so it still demands a free-text
    resume and still fails loudly when the model returns nothing, rather than
    quietly handing back a deterministic document the caller did not ask for.
    """
    profile = await user_service.build_profile_context(session, user)
    if not (profile.resume_text or "").strip():
        raise PreconditionFailedError(
            "Add your resume text in Profile before tailoring — there is nothing to adapt yet."
        )

    row = await derive_for_job(session, user, job_id, strategy=STRATEGY_AI)
    await session.flush()
    logger.info(
        "Tailored resume generated.",
        extra={
            "action": "cv.tailor",
            "status": "ok",
            "user_id": user.id,
            "job_id": job_id,
            "strategy": row.strategy,
            "invention_flags": len(row.invention_flags or []),
            "unsupported": len(row.unsupported_requirements or []),
        },
    )
    return row


async def update_tailored_resume(
    session: AsyncSession, user: User, job_id: int, content: str
) -> TailoredResume:
    """Save the user's edits and re-run the invention guard on the edited text.

    Only `content` moves. `sections`, `focus` and `base_snapshot` describe how
    this version was *derived*, and rewriting them from an edited document would
    turn the record of a derivation into a guess about one.
    """
    row = await get_tailored_resume(session, user, job_id)
    if row is None:
        raise NotFoundError("No tailored resume for this job yet. Generate one first.")

    profile = await user_service.build_profile_context(session, user)
    row.content = content
    row.was_edited = True
    # Re-guard the edited text: the user can introduce a claim too.
    row.invention_flags = flag_unsupported_skills(profile_source_text(profile), content)
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


# --------------------------------------------------------------------------- #
# The application-scoped view of the same row
# --------------------------------------------------------------------------- #


async def _resolve_application(
    session: AsyncSession, user: User, application_id: int
) -> Application:
    from app.services import application_service

    return await application_service.get_application(session, user, application_id)


async def get_for_application(
    session: AsyncSession, user: User, application_id: int
) -> tuple[Application, TailoredResume | None]:
    """This application's resume version, or None when it has none yet.

    None is a normal state, not an error: an application prepared before this
    feature existed simply has no version, and the screen offers to build one
    from the current master instead of breaking.
    """
    application = await _resolve_application(session, user, application_id)
    return application, await get_tailored_resume(session, user, application.job_id)


async def derive_for_application(
    session: AsyncSession,
    user: User,
    application_id: int,
    *,
    strategy: Strategy = STRATEGY_DETERMINISTIC,
) -> tuple[Application, TailoredResume]:
    """Build this application's own version of the resume."""
    application = await _resolve_application(session, user, application_id)
    row = await derive_for_job(session, user, application.job_id, strategy=strategy)
    await session.flush()
    logger.info(
        "Application resume derived.",
        extra={
            "action": "application.resume.derive",
            "status": "ok",
            "user_id": user.id,
            "application_id": application.id,
            "job_id": application.job_id,
            "strategy": row.strategy,
            "keywords": len((row.focus or {}).get("keywords") or []),
        },
    )
    return application, row


async def update_for_application(
    session: AsyncSession, user: User, application_id: int, content: str
) -> tuple[Application, TailoredResume]:
    """Save the user's edits to *this* application's version and nothing else."""
    application = await _resolve_application(session, user, application_id)
    row = await update_tailored_resume(session, user, application.job_id, content)
    return application, row


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #


def _changes_out(row: TailoredResume) -> list[CVChangeOut]:
    return [
        CVChangeOut(
            section=str(change.get("section", "")),
            action=str(change.get("action", "")),
            detail=str(change.get("detail", "")),
        )
        for change in (row.changes or [])
    ]


def to_read(row: TailoredResume, *, current: str | None) -> TailoredResumeRead:
    """Build the job-scoped response, computing staleness against the profile."""
    stale = bool(row.source_fingerprint and current and row.source_fingerprint != current)
    return TailoredResumeRead(
        job_id=row.job_id,
        content=row.content,
        changes=_changes_out(row),
        unsupported_requirements=list(row.unsupported_requirements or []),
        invention_flags=list(row.invention_flags or []),
        stretch_flags=list(row.stretch_flags or []),
        summary=row.summary,
        model=row.model,
        was_edited=row.was_edited,
        is_stale=stale,
        strategy=row.strategy or STRATEGY_AI,
        sections=ResumeSectionsOut.model_validate(row.sections) if row.sections else None,
        focus=ResumeFocusOut.model_validate(row.focus) if row.focus else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_application_read(
    application: Application, row: TailoredResume, *, current: str | None
) -> ApplicationResumeRead:
    """The same version, addressed as the application's own.

    Carries the vacancy's title and company so the screen can say which posting
    this version was built for without a second request — the question the user
    asks first when they have five of these open.
    """
    job = application.job
    return ApplicationResumeRead(
        **to_read(row, current=current).model_dump(),
        application_id=application.id,
        job_title=job.title if job else None,
        job_company=job.company if job else None,
    )
