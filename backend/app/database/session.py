"""SQLAlchemy async engine and sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.database.base import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _enforce_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """Turn `ON DELETE CASCADE` from decoration into behaviour.

    SQLite ships with foreign keys **off** and the setting is per connection,
    so every `ondelete="CASCADE"` in the models — and there is one on almost
    every table — does nothing until this pragma runs. Deleting an account left
    its profile, its jobs and its applications behind, and the orphans are not
    merely wasted rows: ids are reused, so the next account to be handed that id
    collided with the previous owner's profile on a UNIQUE constraint.

    The test suite has always set this pragma (see `tests/conftest.py`), which
    is exactly why the gap survived: the behaviour under test was never the
    behaviour in production.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.resolved_database_url
        kwargs: dict[str, object] = {"echo": settings.debug, "future": True}
        is_sqlite = url.startswith("sqlite")
        if is_sqlite:
            # SQLite must allow use across tasks; the async engine serializes access.
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["pool_pre_ping"] = True
        _engine = create_async_engine(url, **kwargs)
        if is_sqlite:
            _enforce_sqlite_foreign_keys(_engine)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, autoflush=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed at the end."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Session for use outside a request (automation engine, scripts)."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """Create the missing tables.

    A convenience for development and for anyone running without Alembic; the
    canonical path for schema evolution is `alembic upgrade head`.
    """
    import app.models  # noqa: F401  (registers the models in the metadata)

    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        # Less write locking when the API and the engine write at the same time.
        async with engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
