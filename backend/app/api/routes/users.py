"""The current account: its LinkedIn connection, its audit trail, and its erasure."""

# No `from __future__ import annotations` here, for the reason spelled out in
# `routes/auth.py`: slowapi wraps the rate-limited endpoint below, and FastAPI
# would resolve string annotations against slowapi's module globals.

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.api.deps import CurrentUser, LimitDep, SessionDep, limiter
from app.config import get_settings
from app.observability import get_logger
from app.schemas.user import (
    AccountDeleteRequest,
    AuditEventRead,
    LinkedInAccountRead,
    UserRead,
)
from app.services import automation_service, user_service

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()


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


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.rate_limit_auth)
async def delete_current_account(
    request: Request,
    payload: AccountDeleteRequest,
    background: BackgroundTasks,
    user: CurrentUser,
    session: SessionDep,
) -> Response:
    """Erase this account and everything attached to it. Irreversible.

    Profile, resume, job preferences, searches, scored jobs, applications, the
    encrypted LinkedIn session and the audit trail all go. So do the files:
    the uploaded CV, every rendered per-application PDF, and the browser profile
    directory the LinkedIn session lived in. Nothing is retained, and nothing is
    recoverable — there is no soft delete and no grace period behind this.

    Three things happen in order, and the order is the design:

    1. **The automation is stopped first.** A live run holds rows this request is
       about to delete and a browser holding the profile directory open, and
       neither would survive the deletion cleanly.
    2. **The rows go in this transaction**, by cascade.
    3. **The files go after it commits**, from a background task, so a failure
       between the two leaves an intact account rather than an account whose CV
       and session have already been destroyed.

    Rate-limited like the auth routes: it verifies a password, so it is a
    brute-force surface like the login is.
    """
    try:
        await automation_service.stop_all(session, user)
        await automation_service.stop_session(session, user)
    except Exception as exc:
        # Never a reason to refuse the deletion: the engine may be unavailable,
        # or there may be nothing running at all. Recorded because a browser
        # left open is why a profile directory would fail to purge later.
        logger.warning(
            "Could not stop this account's automation before deleting it.",
            exc_info=exc,
            extra={"action": "account.delete", "status": "degraded", "user_id": user.id},
        )

    paths = await user_service.delete_account(session, user, password=payload.password)
    background.add_task(user_service.purge_account_files, paths)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
