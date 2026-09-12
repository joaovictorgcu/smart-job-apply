"""`ON DELETE CASCADE` has to actually cascade.

SQLite ships with foreign keys **off**, per connection. Every `ondelete=
"CASCADE"` in the models was therefore decoration in production: deleting an
account left its profile, its settings and its LinkedIn row behind. Orphans are
not merely untidy — SQLite reuses row ids, so the next account handed a freed id
collided with the previous owner's profile on a UNIQUE constraint, and creating
a user failed with an error naming a table nobody had touched.

The test suite set this pragma from the start, which is precisely why the gap
lasted: the behaviour under test was never the behaviour being shipped. These
tests exercise the production helper instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database.base import Base
from app.database.session import _enforce_sqlite_foreign_keys


@pytest.fixture
async def guarded_engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """An engine built the way `get_engine` builds one for SQLite."""
    import app.models  # noqa: F401  (registers the tables)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'fk.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    _enforce_sqlite_foreign_keys(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_the_pragma_is_on_for_every_connection(
    guarded_engine: AsyncEngine,
) -> None:
    """Per connection, so one checked-out connection proves nothing on its own."""
    for _ in range(3):
        async with guarded_engine.connect() as connection:
            enabled = (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one()
            assert enabled == 1


async def test_deleting_an_account_takes_its_rows_with_it(
    guarded_engine: AsyncEngine,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models import Profile, User, UserSettings

    maker = async_sessionmaker(guarded_engine, expire_on_commit=False)
    async with maker() as session:
        user = User(email="gone@example.com", hashed_password="x")
        session.add(user)
        await session.flush()
        session.add(Profile(user_id=user.id))
        session.add(UserSettings(user_id=user.id))
        await session.commit()
        user_id = user.id

    async with maker() as session:
        # Raw DELETE rather than the ORM's own cascade: what is under test is
        # the database enforcing the constraint, not SQLAlchemy emitting extra
        # statements it would emit anyway.
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await session.commit()

    async with maker() as session:
        for table in ("profiles", "user_settings"):
            left = (
                await session.execute(
                    text(f"SELECT count(*) FROM {table} WHERE user_id = :id"),
                    {"id": user_id},
                )
            ).scalar_one()
            assert left == 0, f"{table} kept a row for a user that no longer exists"


async def test_an_unguarded_engine_would_have_kept_the_orphan(
    tmp_path: Path,
) -> None:
    """The bug, reproduced — so the fix is not mistaken for a no-op.

    Same schema, same delete, no pragma: the profile survives its owner. This is
    the production behaviour every release before this one had.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.models  # noqa: F401
    from app.models import Profile, User

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'loose.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            user = User(email="ghost@example.com", hashed_password="x")
            session.add(user)
            await session.flush()
            session.add(Profile(user_id=user.id))
            await session.commit()
            user_id = user.id

        async with maker() as session:
            await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
            await session.commit()

        async with maker() as session:
            orphans = (
                await session.execute(
                    text("SELECT count(*) FROM profiles WHERE user_id = :id"),
                    {"id": user_id},
                )
            ).scalar_one()
        assert orphans == 1
    finally:
        await engine.dispose()
