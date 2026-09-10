"""The account's standing answer to "what kind of vacancy am I looking for".

Three things hang off it, and the split between them is the same one the rest
of the app uses: `app.domain.preferences` decides *what* the rules mean, this
module decides *when* they are stored and what else moves with them.

1. **The query.** Saving preferences keeps one managed saved search in step
   with them, so a new account has something to run without ever opening the
   search form.
2. **The triage.** `rules_for` hands the scoring path a plain dataclass, so a
   posting the user already ruled out never costs a model call.
3. **The emphasis.** `priority_technologies` rides into the resume derivation
   as extra vocabulary — it can only re-rank terms the candidate already
   claims, never add one.

Nothing here commits: the request session commits once, at the end.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import preferences as domain
from app.models import AuditAction, JobPreferences, Search, User
from app.observability import get_logger, record_audit_event
from app.schemas.job import SearchCreate
from app.schemas.preferences import JobPreferencesUpdate
from app.services import search_service

logger = get_logger(__name__)

# The saved search kept in step with the preferences. Matched by name, because
# that is what the user sees in the list and therefore what they would rename
# if they wanted to take it over.
MANAGED_SEARCH_NAME = "Minhas vagas"


async def get_or_create(session: AsyncSession, user: User) -> JobPreferences:
    """This account's preferences, empty on first access.

    Empty is a meaningful state, not a placeholder: nothing stated means
    nothing may be ruled out, which `domain.preferences.screen` enforces.
    """
    result = await session.execute(
        select(JobPreferences).where(JobPreferences.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = JobPreferences(user_id=user.id)
        session.add(row)
        await session.flush()
    return row


def to_rules(row: JobPreferences | None) -> domain.JobPreferenceRules:
    """The stored row as the plain data the domain reasons about."""
    if row is None:
        return domain.JobPreferenceRules()
    return domain.JobPreferenceRules(
        target_role=row.target_role or "",
        alternative_roles=tuple(row.alternative_roles or []),
        seniority=tuple(row.seniority or []),
        work_models=tuple(row.work_models or []),
        locations=tuple(row.locations or []),
        salary_min=row.salary_min,
        salary_currency=row.salary_currency or "BRL",
        priority_technologies=tuple(row.priority_technologies or []),
        excluded_terms=tuple(row.excluded_terms or []),
    )


async def rules_for(session: AsyncSession, user_id: int) -> domain.JobPreferenceRules:
    """The rules for one user id, without needing the `User` row loaded.

    Used from the scoring path, which has an id and a job and no reason to
    fetch anything else.
    """
    result = await session.execute(
        select(JobPreferences).where(JobPreferences.user_id == user_id)
    )
    return to_rules(result.scalar_one_or_none())


async def update(
    session: AsyncSession, user: User, payload: JobPreferencesUpdate
) -> JobPreferences:
    """Apply the fields the client sent, then keep the managed search in step."""
    row = await get_or_create(session, user)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(field for field, value in changes.items() if getattr(row, field) != value)

    for field, value in changes.items():
        setattr(row, field, value)
    await session.flush()

    await sync_managed_search(session, user, row)

    if changed:
        # Field names only, in keeping with the rest of the trail: what someone
        # is looking for is theirs, and an append-only table nobody can edit is
        # the wrong place to copy it into.
        await record_audit_event(
            session,
            user_id=user.id,
            action=AuditAction.PROFILE_UPDATED,
            subject_type="job_preferences",
            subject_id=row.id,
            after={"fields": changed},
        )
    logger.info(
        "Job preferences updated.",
        extra={
            "action": "preferences.update",
            "status": "ok",
            "user_id": user.id,
            "fields": changed,
        },
    )
    return row


async def sync_managed_search(
    session: AsyncSession, user: User, row: JobPreferences
) -> Search | None:
    """Keep one saved search in step with the preferences.

    The point is that a new account never has to open the search form: state a
    role, and there is something to run. It is rewritten from the preferences
    on every save and is therefore not a place to keep hand edits — renaming it
    is how a user takes it over, after which this creates a fresh one.

    Returns None when there is no role yet: a search with empty keywords would
    sweep everything, which is the opposite of what a preference is for.
    """
    rules = to_rules(row)
    keywords = domain.search_keywords(rules)
    if not keywords:
        return None

    existing = await session.execute(
        select(Search).where(Search.user_id == user.id, Search.name == MANAGED_SEARCH_NAME)
    )
    search = existing.scalar_one_or_none()

    location = domain.search_location(rules)
    remote_filter = domain.search_remote_filter(rules)
    levels = list(rules.seniority)

    if search is None:
        return await search_service.create_search(
            session,
            user,
            SearchCreate(
                name=MANAGED_SEARCH_NAME,
                keywords=keywords,
                location=location,
                remote_filter=remote_filter,
                experience_levels=levels,
                easy_apply_only=True,
            ),
        )

    search.keywords = keywords
    search.location = location
    search.remote_filter = remote_filter
    search.experience_levels = levels
    await session.flush()
    return search
