"""Read-only views of the current account, its LinkedIn connection and its audit trail."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, LimitDep, SessionDep
from app.schemas.user import AuditEventRead, LinkedInAccountRead, UserRead
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_current_user(user: CurrentUser) -> UserRead:
    """Same payload as `/api/auth/me`, for clients that group user data here."""
    return UserRead.model_validate(user)


@router.get("/me/audit", response_model=list[AuditEventRead])
async def read_audit_trail(
    user: CurrentUser, session: SessionDep, limit: LimitDep = 50
) -> list[AuditEventRead]:
    """Changes recorded for this account, newest first.

    Mostly guardrail changes: turning off dry-run, raising the daily cap, lowering
    the minimum score. Each entry carries the fields that moved and which of them
    were loosened.
    """
    events = await user_service.list_audit_events(session, user, limit=limit)
    return [AuditEventRead.model_validate(event) for event in events]


@router.get("/me/linkedin", response_model=LinkedInAccountRead)
async def read_linkedin_account(user: CurrentUser, session: SessionDep) -> LinkedInAccountRead:
    """Metadata about the stored LinkedIn session.

    Only whether a session exists and when it was last verified — the encrypted
    cookies never leave the server, and no password is ever stored.
    """
    account = await user_service.get_linkedin_account(session, user)
    if account is None:
        return LinkedInAccountRead()
    return LinkedInAccountRead.model_validate(account)
