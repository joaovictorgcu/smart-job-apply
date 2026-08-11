"""Automation guardrails and AI preferences."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.schemas.user import UserSettingsRead, UserSettingsUpdate
from app.services import user_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsRead)
async def read_settings(user: CurrentUser, session: SessionDep) -> UserSettingsRead:
    """Return the guardrails in force for this account."""
    user_settings = await user_service.get_or_create_settings(session, user)
    return UserSettingsRead.model_validate(user_settings)


@router.put("", response_model=UserSettingsRead)
async def update_settings(
    payload: UserSettingsUpdate, user: CurrentUser, session: SessionDep
) -> UserSettingsRead:
    """Update the guardrails.

    Only the fields present in the body change, and the merged result is validated:
    delay and working-hour ranges must stay consistent. Manual approval cannot be
    disabled while the deployment runs in assisted mode.
    """
    user_settings = await user_service.update_settings(session, user, payload)
    return UserSettingsRead.model_validate(user_settings)
