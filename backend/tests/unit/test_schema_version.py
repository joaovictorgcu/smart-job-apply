"""The check that would have caught the outage in one line.

Migration 0014 added two columns to `user_settings`. The database had never been
migrated, `create_all` cannot add a column to a table that already exists, and
so the server started, logged "API started", reported itself healthy, and
answered 500 to every request that loaded a settings row.

Nothing in the app asked whether the schema matched the code. These tests pin
the answer, including the two states that are *not* failures: a database at head,
and one created by `create_all` that simply carries no stamp.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.database.schema_version import (
    SchemaState,
    read_schema_status,
)


@pytest.fixture
async def connection(tmp_path: Path) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'schema.db').as_posix()}", future=True
    )
    async with engine.connect() as conn:
        yield conn
    await engine.dispose()


async def _stamp(connection: AsyncConnection, revision: str) -> None:
    await connection.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
    )
    await connection.execute(text("DELETE FROM alembic_version"))
    await connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:rev)"), {"rev": revision}
    )
    await connection.commit()


async def test_a_database_at_head_is_current(connection: AsyncConnection) -> None:
    from app.database.schema_version import _head_revision

    head = _head_revision()
    assert head is not None, "the migration tree should have a head"
    await _stamp(connection, head)

    status = await read_schema_status(connection)

    assert status.state is SchemaState.CURRENT
    assert status.needs_action is False
    assert status.pending == ()


async def test_a_database_behind_head_names_what_is_missing(
    connection: AsyncConnection,
) -> None:
    """The exact situation that broke the app: stamped 0012, code at 0014."""
    await _stamp(connection, "0012")

    status = await read_schema_status(connection)

    assert status.state is SchemaState.BEHIND
    assert status.needs_action is True
    assert status.current == "0012"
    # Naming them is the point — "some migrations are pending" sends the reader
    # looking for which. In the order they will be applied, which is the order
    # the operator is about to watch scroll past.
    assert status.pending == ("0013", "0014")
    assert "alembic upgrade head" in status.summary


async def test_an_unstamped_database_says_how_to_stamp_it(
    connection: AsyncConnection,
) -> None:
    """A `create_all` database is not broken, it is unlabelled.

    Reporting it as "behind" would send someone to run migrations against a
    schema that already has every table, which is how the collision that needed
    `alembic stamp` in the first place gets created again.
    """
    status = await read_schema_status(connection)

    assert status.state is SchemaState.UNSTAMPED
    assert status.current is None
    assert "alembic stamp head" in status.summary


async def test_the_probe_never_raises(tmp_path: Path) -> None:
    """A diagnostic that can take the process down is worse than none."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'gone.db').as_posix()}", future=True
    )
    async with engine.connect() as conn:
        await conn.close()
        status = await read_schema_status(conn)
    await engine.dispose()

    assert status.state in (SchemaState.UNKNOWN, SchemaState.UNSTAMPED)
