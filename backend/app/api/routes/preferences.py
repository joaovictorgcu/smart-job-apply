"""What kind of vacancy this account is looking for."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.preferences import JobPreferencesRead, JobPreferencesUpdate
from app.services import preference_service

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=JobPreferencesRead)
async def read_preferences(user: CurrentUser, session: SessionDep) -> JobPreferencesRead:
    """The stated preferences, empty on first access.

    Empty is meaningful rather than unset: nothing stated means nothing is
    ruled out, and no posting is skipped for a reason the user never gave.
    """
    row = await preference_service.get_or_create(session, user)
    return JobPreferencesRead.model_validate(row)


@router.put("", response_model=JobPreferencesRead)
async def update_preferences(
    payload: JobPreferencesUpdate, user: CurrentUser, session: SessionDep
) -> JobPreferencesRead:
    """Update the preferences. Only the fields present in the body are touched.

    Saving also keeps one managed saved search ("Minhas vagas") in step with
    the stated role, so there is something to run without opening the search
    form. That search is rewritten from here on every save; renaming it is how
    a user takes it over.
    """
    row = await preference_service.update(session, user, payload)
    return JobPreferencesRead.model_validate(row)
