"""FastAPI dependencies that turn a bearer token into the current `User`."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AuthenticationError, PermissionDeniedError
from app.auth.security import TokenError, decode_access_token
from app.database import get_session, session_scope
from app.models import User
from app.observability import bind_context, get_logger

logger = get_logger(__name__)

# auto_error=False so a missing header reaches our own handler and produces the
# same `{"detail": ...}` body as every other failure.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT issued by /api/auth/login")

WS_INVALID_TOKEN_CODE = 4401


async def _user_from_token(session: AsyncSession, token: str) -> User:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (TokenError, KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired token.") from exc

    user = await session.get(User, user_id)
    if user is None:
        raise AuthenticationError("Invalid or expired token.")
    if not user.is_active:
        raise PermissionDeniedError("This account is disabled.")
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    """Resolve the authenticated user, or fail with 401/403."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token.")
    user = await _user_from_token(session, credentials.credentials)
    bind_context(user_id=user.id)
    return user


async def get_current_user_ws(websocket: WebSocket, token: str | None) -> User | None:
    """Authenticate a WebSocket handshake from the `?token=` query parameter.

    Returns `None` after closing the socket with 4401 so the frontend can tell an
    auth failure from a network drop and stop retrying with a stale token. The
    socket is accepted first because a close code is only delivered to the client
    once the handshake completed.
    """
    if not token:
        await websocket.accept()
        await websocket.close(code=WS_INVALID_TOKEN_CODE, reason="Missing token.")
        return None

    # Its own short-lived session: a socket lives for hours and must not hold a
    # database connection open for that long.
    try:
        async with session_scope() as session:
            user = await _user_from_token(session, token)
    except (AuthenticationError, PermissionDeniedError) as exc:
        logger.warning(
            "WebSocket authentication rejected.",
            extra={"action": "ws.auth", "status": "rejected", "error_type": type(exc).__name__},
        )
        await websocket.accept()
        await websocket.close(code=WS_INVALID_TOKEN_CODE, reason=exc.detail)
        return None

    bind_context(user_id=user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

__all__ = [
    "WS_INVALID_TOKEN_CODE",
    "CurrentUser",
    "SessionDep",
    "bearer_scheme",
    "get_current_user",
    "get_current_user_ws",
]
