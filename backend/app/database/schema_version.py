"""Is the database schema the one this code was written against?

The app has two ways to get a schema, and that is the whole problem. `init_models`
runs `create_all`, which creates *missing tables* and never a missing column;
Alembic owns real evolution. A database that was migrated once and then grew by
`create_all` therefore ends up in a state neither tool describes: new tables
present, new columns absent, and a version stamp pointing at the past.

That state is not theoretical. It took the whole application down: migration
0014 added two columns to `user_settings`, `create_all` could not add them, and
every endpoint that loaded a settings row — stats, AI status, settings, the
session banner — answered 500 with `no such column: user_settings.ai_provider`.
The server started perfectly and reported itself healthy the entire time.

So this module answers the question nobody was asking at startup, and the answer
is surfaced on the admin panel's database row rather than only in a log line.

It deliberately does **not** migrate anything. Running DDL against somebody's
data as a side effect of starting a process is a decision for an operator, not
a convenience for a framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import BACKEND_DIR
from app.observability import get_logger

logger = get_logger(__name__)

MIGRATIONS_DIR = BACKEND_DIR / "migrations"

# What to run when it is behind. Quoted in the log, on the panel and in the docs
# so nobody has to go looking for it mid-incident.
UPGRADE_COMMAND = "cd backend && alembic upgrade head"
STAMP_COMMAND = "cd backend && alembic stamp head"


class SchemaState(StrEnum):
    CURRENT = "current"  # stamped at head — the only fully known-good state
    BEHIND = "behind"  # stamped, but at an older revision: migrations pending
    UNSTAMPED = "unstamped"  # no alembic_version row, e.g. created by create_all
    UNKNOWN = "unknown"  # the check itself could not run


@dataclass(frozen=True)
class SchemaStatus:
    state: SchemaState
    current: str | None
    head: str | None
    pending: tuple[str, ...] = ()

    @property
    def needs_action(self) -> bool:
        """Only a stamped-but-behind database is actually wrong.

        A database with no stamp was built by `create_all` from the current
        models: its schema *is* the code's, it merely carries no label. Calling
        that a problem would fire a warning on every fresh install and on every
        test database, and a warning that is usually wrong is one nobody reads
        on the day it is right.
        """
        return self.state is SchemaState.BEHIND

    @property
    def summary(self) -> str:
        """One line, written for whoever is staring at a broken deployment."""
        if self.state is SchemaState.CURRENT:
            return f"Schema na revisão {self.current}."
        if self.state is SchemaState.BEHIND:
            count = len(self.pending)
            names = ", ".join(self.pending) if self.pending else "?"
            return (
                f"{count} migration(s) pendente(s) ({names}). O schema está em "
                f"{self.current} e o código espera {self.head}. Rode: {UPGRADE_COMMAND}"
            )
        if self.state is SchemaState.UNSTAMPED:
            return (
                "Banco sem registro de migration. Se ele foi criado pelo próprio app "
                f"(create_all), rode: {STAMP_COMMAND}"
            )
        return "Não foi possível verificar a revisão do schema."


def _head_revision() -> str | None:
    """The newest revision on disk, read without starting Alembic's runtime."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError:  # pragma: no cover - alembic is a declared dependency
        return None

    if not MIGRATIONS_DIR.is_dir():
        return None
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    try:
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:  # noqa: BLE001 - a malformed tree must not stop the app
        return None


def _pending_between(current: str | None, head: str | None) -> tuple[str, ...]:
    """Revisions between what the database has and what the code expects.

    Best effort: it exists so the message can name the migrations instead of
    saying "some". A walk that fails costs the detail, never the verdict.
    """
    if current is None or head is None or current == head:
        return ()
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config()
        config.set_main_option("script_location", str(MIGRATIONS_DIR))
        script = ScriptDirectory.from_config(config)
        # `iterate_revisions` walks backwards from head; reversed, the list
        # reads in the order they will be applied, which is the order the
        # operator is about to see scroll past.
        return tuple(
            reversed(
                [
                    revision.revision
                    for revision in script.iterate_revisions(head, current)
                    if revision.revision != current
                ]
            )
        )
    except Exception:  # noqa: BLE001
        return ()


async def read_schema_status(connection: AsyncConnection) -> SchemaStatus:
    """Compare the database's stamp against the newest migration on disk."""
    head = _head_revision()
    try:
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        if "alembic_version" not in tables:
            return SchemaStatus(state=SchemaState.UNSTAMPED, current=None, head=head)
        current = (
            await connection.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001 - a probe must never be the thing that fails
        logger.warning(
            "Could not read the schema revision.",
            extra={"action": "schema.check", "status": "unknown", "error": str(exc)},
        )
        return SchemaStatus(state=SchemaState.UNKNOWN, current=None, head=head)

    if head is not None and current == head:
        return SchemaStatus(state=SchemaState.CURRENT, current=current, head=head)
    return SchemaStatus(
        state=SchemaState.BEHIND,
        current=current,
        head=head,
        pending=_pending_between(current, head),
    )


async def log_schema_status(connection: AsyncConnection) -> SchemaStatus:
    """Check at startup and say so, loudly enough to be found.

    The process keeps serving either way. Refusing to boot would have made the
    original incident *worse*: the admin panel is where the problem is now
    visible, and a server that will not start cannot show it to anybody.
    """
    status = await read_schema_status(connection)
    if status.state is SchemaState.BEHIND:
        logger.error(
            "The database schema is behind the code. %s",
            status.summary,
            extra={
                "action": "schema.check",
                "status": "behind",
                "current": status.current,
                "head": status.head,
                "pending": list(status.pending),
            },
        )
    elif status.state is SchemaState.UNSTAMPED:
        logger.warning(
            "The database has no migration stamp. %s",
            status.summary,
            extra={"action": "schema.check", "status": "unstamped", "head": status.head},
        )
    else:
        logger.info(
            "Schema checked.",
            extra={
                "action": "schema.check",
                "status": str(status.state),
                "current": status.current,
            },
        )
    return status


__all__ = [
    "MIGRATIONS_DIR",
    "STAMP_COMMAND",
    "UPGRADE_COMMAND",
    "SchemaState",
    "SchemaStatus",
    "log_schema_status",
    "read_schema_status",
]
