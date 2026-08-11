"""Saved searches — CRUD, always scoped to the owning user."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import NotFoundError
from app.automation.contracts import SearchFilters
from app.database.base import utcnow
from app.models import Search, User
from app.observability import get_logger
from app.schemas.job import SearchCreate, SearchUpdate

logger = get_logger(__name__)


async def list_searches(session: AsyncSession, user: User) -> list[Search]:
    result = await session.execute(
        select(Search).where(Search.user_id == user.id).order_by(Search.created_at.desc())
    )
    return list(result.scalars().all())


async def get_search(session: AsyncSession, user: User, search_id: int) -> Search:
    """Load a search owned by this user, or raise `NotFoundError`.

    The ownership filter lives here so no route can forget it.
    """
    result = await session.execute(
        select(Search).where(Search.id == search_id, Search.user_id == user.id)
    )
    search = result.scalar_one_or_none()
    if search is None:
        raise NotFoundError("Search not found.")
    return search


async def create_search(session: AsyncSession, user: User, payload: SearchCreate) -> Search:
    search = Search(user_id=user.id, **payload.model_dump())
    session.add(search)
    await session.flush()
    logger.info(
        "Search created.",
        extra={"action": "search.create", "status": "ok", "user_id": user.id, "search_id": search.id},
    )
    return search


async def update_search(
    session: AsyncSession, user: User, search_id: int, payload: SearchUpdate
) -> Search:
    search = await get_search(session, user, search_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(search, field, value)
    await session.flush()
    return search


async def delete_search(session: AsyncSession, user: User, search_id: int) -> None:
    search = await get_search(session, user, search_id)
    await session.execute(delete(Search).where(Search.id == search.id))
    logger.info(
        "Search deleted.",
        extra={"action": "search.delete", "status": "ok", "user_id": user.id, "search_id": search_id},
    )


async def touch_last_run(session: AsyncSession, user: User, search_id: int) -> Search:
    search = await get_search(session, user, search_id)
    search.last_run_at = utcnow()
    await session.flush()
    return search


async def count_searches(session: AsyncSession, user: User) -> int:
    result = await session.execute(
        select(func.count()).select_from(Search).where(Search.user_id == user.id)
    )
    return int(result.scalar_one())


def to_filters(search: Search, *, max_results: int | None = None) -> SearchFilters:
    """Convert a saved search into the automation layer's filter contract."""
    return SearchFilters(
        keywords=search.keywords,
        location=search.location,
        remote_filter=search.remote_filter,
        date_posted=search.date_posted,
        experience_levels=list(search.experience_levels or []),
        easy_apply_only=search.easy_apply_only,
        max_results=max_results or search.max_results,
    )
