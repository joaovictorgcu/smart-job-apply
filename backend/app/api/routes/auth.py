"""Application authentication. Nothing here touches LinkedIn credentials."""

# No `from __future__ import annotations` here: slowapi wraps these endpoints, and
# FastAPI would then resolve the string annotations against slowapi's module globals
# instead of this one.

from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, SessionDep, limiter
from app.auth.security import create_access_token
from app.config import get_settings
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _token_response(user_id: int, user: UserRead) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        expires_in=settings.access_token_ttl_minutes * 60,
        user=user,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_auth)
async def register(request: Request, payload: RegisterRequest, session: SessionDep) -> TokenResponse:
    """Create an account with an empty profile and conservative default guardrails.

    The new account starts in dry-run mode with manual approval required, so it
    cannot submit anything before the user configures it.
    """
    user = await user_service.register_user(
        session,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    return _token_response(user.id, UserRead.model_validate(user))


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.rate_limit_auth)
async def login(request: Request, payload: LoginRequest, session: SessionDep) -> TokenResponse:
    """Exchange email and password for a bearer token."""
    user = await user_service.authenticate(
        session, email=payload.email, password=payload.password
    )
    return _token_response(user.id, UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> UserRead:
    """Return the account behind the current token."""
    return UserRead.model_validate(user)
