"""Shared dependencies for the HTTP layer."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_user_ws
from app.config import get_settings
from app.database import get_session
from app.models import User

settings = get_settings()

# Declared here rather than in main.py: the auth routes need the same instance to
# apply a stricter limit, and importing main from a router would be a cycle.
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
LimitDep = Annotated[int, Query(ge=1, le=200, description="Page size.")]
OffsetDep = Annotated[int, Query(ge=0, description="Number of items to skip.")]

__all__ = [
    "CurrentUser",
    "LimitDep",
    "OffsetDep",
    "SessionDep",
    "get_current_user",
    "get_current_user_ws",
    "get_session",
    "limiter",
]
